"""One authorized ingestion attempt; refuses nonempty collections and never retries."""
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from app.rag.vector_store import qdrant_client as q
from app.rag.embedding import embedding_service as emb
from app.rag.ingestion import ingestion_service as ingest
from app.rag.ingestion.parser import parse_devices
from app.rag.ingestion.chunker import chunk_all_devices
from qdrant_client.common.version_check import is_compatible

SOURCE = ROOT / "app/rag/data/devices.txt"
EXPECTED_SOURCE = "dedffbfdabc6fb7f227681f5913248919ec45274c626bfe60da24f8cd248a3a0"
EXPECTED_ENDPOINT = "f42f90901293666b7bac0bc988397670f17d3a3786b7436ea091090f282eedd0"
result = {"date": "2026-11-08", "source": "app/rag/data/devices.txt",
          "embedding_model": emb.MODEL, "embedding_requests_attempted": 0,
          "embedding_requests_succeeded": 0, "embedding_tokens": 0,
          "ingestion_invocations": 0, "automatic_retries": 0}

def save():
    (OUT / "ingestion.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def safe_error(exc):
    chain = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        code = getattr(exc, "code", None)
        if code not in {"invalid_api_key", "insufficient_quota", "rate_limit_exceeded",
                        "model_not_found", "unsupported_parameter", "unsupported_value"}:
            code = None
        chain.append({"type": type(exc).__name__, "http_status": getattr(exc, "status_code", None), "code": code})
        exc = exc.__cause__ or exc.__context__
    return chain

try:
    assert not (OUT / "ingestion_started.json").exists(), "This attempt already ran; do not repeat"
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED_SOURCE
    assert hashlib.sha256(q.QDRANT_URL.encode()).hexdigest() == EXPECTED_ENDPOINT
    assert q.COLLECTION == "devices" and emb.MODEL == "text-embedding-3-large"
    server = q.client.info().version
    assert is_compatible(version("qdrant-client"), server), "Incompatible client/server"
    result["client_version"], result["server_version"] = version("qdrant-client"), server
    names = [c.name for c in q.client.get_collections().collections]
    result["collections_before"] = names
    if "devices" in names:
        assert q.client.count("devices", exact=True).count == 0, "Nonempty collection; preserve existing points"
        vectors = q.client.get_collection("devices").config.params.vectors
        assert vectors.size == 3072 and vectors.distance.value == "Cosine"
    devices = parse_devices(SOURCE.read_text(encoding="utf-8"))
    chunks = chunk_all_devices(devices)
    assert len(devices) == 10 and len(chunks) == 40
    expected = {}
    for i, chunk in enumerate(chunks):
        chunk.source, chunk.doc_type = "devices.txt", "device_txt"
        expected[ingest._point_id(chunk, i)] = {"name": chunk.name, "section": chunk.section,
            "text": chunk.text, "source": chunk.source, "doc_type": chunk.doc_type}
    assert len(expected) == 40
    result["expected_devices"], result["expected_points"] = 10, 40
    with (OUT / "ingestion_started.json").open("x", encoding="utf-8") as stream:
        json.dump({"source_sha256": EXPECTED_SOURCE, "endpoint_fingerprint": EXPECTED_ENDPOINT,
                   "source": result["source"], "expected_points": 40}, stream, indent=2)
    emb.client = emb._get_client().with_options(max_retries=0, timeout=30)
    actual_create = emb.client.embeddings.create
    def measured_create(*args, **kwargs):
        position = result["embedding_requests_attempted"]
        assert kwargs["input"] == chunks[position].text
        result["embedding_requests_attempted"] += 1
        response = actual_create(*args, **kwargs)
        vector = response.data[0].embedding
        assert len(vector) == 3072 and all(math.isfinite(v) for v in vector)
        result["embedding_requests_succeeded"] += 1
        result["embedding_tokens"] += response.usage.total_tokens
        if result["embedding_requests_succeeded"] % 5 == 0:
            print(json.dumps({"embedding_completed": result["embedding_requests_succeeded"], "of": 40}), flush=True)
            save()
        return response
    with patch.object(emb.client.embeddings, "create", side_effect=measured_create):
        result["ingestion_invocations"] = 1
        result["ingest_returned_points"] = ingest.ingest_devices(str(SOURCE))
    info = q.client.get_collection("devices")
    count = q.client.count("devices", exact=True).count
    points, offset = q.client.scroll("devices", limit=100, with_payload=True, with_vectors=True)
    assert count == len(points) == 40 and offset is None
    assert {str(p.id) for p in points} == set(expected)
    assert all(p.payload == expected[str(p.id)] for p in points)
    assert all(isinstance(p.vector, list) and len(p.vector) == 3072 for p in points)
    assert info.config.params.vectors.size == 3072 and info.config.params.vectors.distance.value == "Cosine"
    assert "name" in info.payload_schema and info.payload_schema["name"].data_type.value == "keyword"
    result.update(status="succeeded", verified_points=count, payloads_exactly_match_source=True,
                  vector_size=3072, distance="Cosine", name_index="keyword",
                  source_sha256=EXPECTED_SOURCE,
                  device_names=sorted({p.payload["name"] for p in points}),
                  points=[{"id":str(p.id), "name":p.payload["name"], "section":p.payload["section"],
                           "payload_sha256":hashlib.sha256(json.dumps(p.payload, sort_keys=True).encode()).hexdigest()}
                          for p in sorted(points,key=lambda p:str(p.id))])
except Exception as exc:
    result.update(status="stopped_on_error", error_chain=safe_error(exc))
    try:
        exists=q.client.collection_exists("devices")
        result["devices_exists_after_error"]=exists
        result["verified_points"]=q.client.count("devices",exact=True).count if exists else None
    except Exception as inspection:
        result["readback_error_chain"]=safe_error(inspection)
finally:
    save()
    q.client.close()
print(json.dumps({k:v for k,v in result.items() if k not in ("points", "source_sha256")}), flush=True)
raise SystemExit(0 if result.get("status")=="succeeded" else 1)
