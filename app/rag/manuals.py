"""Small, reviewed manifest for manufacturer PDF excerpts; no network on import."""
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/model_manuals/manifest.json"
PDF_DIRECTORY = ROOT / ".cache/official_manuals"
MANUAL_TYPE = "manufacturer_manual"
POINT_NAMESPACE = UUID("427c0f18-caf4-4072-bda0-e4fb3221d37b")


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not data.get("documents"):
        raise ValueError("Unsupported or empty manual manifest")
    documents = data["documents"]
    names, codes = set(), set()
    for doc in documents:
        if (not isinstance(doc.get("name"), str) or not doc["name"].strip()
                or not isinstance(doc.get("item_code"), str) or not doc["item_code"].strip()
                or doc["name"] in names or doc["item_code"] in codes):
            raise ValueError("Ambiguous manual model identity")
        names.add(doc["name"])
        codes.add(doc["item_code"])
        if (Path(doc["file"]).name != doc["file"] or not doc["file"].endswith(".pdf")
                or len(doc["sha256"]) != 64 or not doc["source_url"].startswith("https://")
                or not doc.get("scope") or not doc.get("selections")):
            raise ValueError("Invalid manual provenance")
        keys = set()
        for selection in doc["selections"]:
            key = (selection["page"], selection["section"])
            if (type(selection["page"]) is not int or not 1 <= selection["page"] <= doc["page_count"]
                    or key in keys):
                raise ValueError("Invalid/duplicate manual selection")
            keys.add(key)
    return documents


def model_document(name: str, item_code: str, documents=None) -> dict | None:
    documents = load_manifest() if documents is None else documents
    return next((d for d in documents if (d["name"], d["item_code"]) == (name, item_code)), None)


def model_status(name: str, item_code: str, documents=None) -> str:
    documents = load_manifest() if documents is None else documents
    if model_document(name, item_code, documents):
        return "documented"
    if any(d["name"] == name or d["item_code"] == item_code for d in documents):
        return "identifier_conflict"
    return "undocumented_model"


def sql_model_pairs(result: dict) -> list[tuple[str, str]]:
    """Identity must come from actual SQL columns, never a question or LLM prose."""
    columns = [str(c).strip().lower() for c in result.get("columns", [])]
    if columns.count("name") != 1 or columns.count("item_code") != 1:
        return []
    ni, ci = columns.index("name"), columns.index("item_code")
    pairs = set()
    for row in result.get("rows", []):
        if max(ni, ci) >= len(row):
            return []
        name, code = row[ni], row[ci]
        if not isinstance(name, str) or not name.strip() or not isinstance(code, str) or not code.strip():
            return []
        pairs.add((name, code))  # Preserve the DB values, including capitalization.
    return sorted(pairs)


def selected_text(text: str, selection: dict) -> str:
    from app.rag.ingestion.document_parser import normalize_text
    start = selection.get("start")
    end = selection.get("end")
    if start:
        if text.count(start) != 1:
            raise ValueError("Manual selection start is missing or ambiguous")
        text = text[text.index(start):]
    if end:
        if text.count(end) != 1:
            raise ValueError("Manual selection end is missing or ambiguous")
        text = text[:text.index(end)]
    text = normalize_text(text)
    if not text:
        raise ValueError("Empty manual selection")
    return text


def prepare_chunks(documents=None, directory: Path = PDF_DIRECTORY):
    from pypdf import PdfReader
    from app.rag.ingestion.chunker import chunk_document_text
    documents = load_manifest() if documents is None else documents
    chunks = []
    for doc in documents:
        path = Path(directory) / doc["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != doc["sha256"]:
            raise ValueError("Manual file hash differs from reviewed document")
        pdf = PdfReader(path)
        if len(pdf.pages) != doc["page_count"]:
            raise ValueError("Manual page count mismatch")
        evidence = doc["model_evidence"]
        identity_text = (pdf.pages[evidence["page"] - 1].extract_text() or "").replace("\u2011", "-").replace("\u2010", "-")
        if evidence["text"] not in identity_text:
            raise ValueError("Model not found on reviewed evidence page")
        for selection in doc["selections"]:
            text = selected_text(pdf.pages[selection["page"] - 1].extract_text() or "", selection)
            # Keep short procedures intact, and never merge different PDF pages.
            for chunk in chunk_document_text(text, source=doc["file"], doc_type=MANUAL_TYPE,
                                             chunk_size=2400, overlap=200):
                chunk.name = doc["name"]
                chunk.item_code = doc["item_code"]
                chunk.source_url = doc["source_url"]
                chunk.source_sha256 = doc["sha256"]
                chunk.page = selection["page"]
                chunk.section = selection["section"] + "/" + chunk.section
                chunks.append(chunk)
    return chunks


def manual_payload(chunk) -> dict:
    from dataclasses import asdict
    return {k: v for k, v in asdict(chunk).items() if v is not None}


def manual_point_id(payload: dict) -> str:
    # Hash all identity, content and selection metadata. Separate from legacy IDs.
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return str(uuid5(POINT_NAMESPACE, digest))


def valid_manual_hit(hit: dict, doc: dict) -> bool:
    return (hit.get("name") == doc["name"] and hit.get("item_code") == doc["item_code"]
            and hit.get("doc_type") == MANUAL_TYPE and hit.get("source_url") == doc["source_url"]
            and hit.get("source_sha256") == doc["sha256"]
            and any(hit.get("page") == s["page"] and
                    str(hit.get("section", "")).startswith(s["section"] + "/chunk-")
                    for s in doc["selections"]))


def index_manual_chunks(client, collection: str, chunks, *, apply=False, embedder=None) -> dict:
    """Dry-run is read-only; unchanged IDs skip embedding and upsert on repeat."""
    import math
    from qdrant_client.models import PointStruct, PayloadSchemaType
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    if not hasattr(vectors, "size") or vectors.size != 3072 or vectors.distance.value != "Cosine":
        raise ValueError("Manual index requires 3072-dimensional Cosine vectors")
    payloads = {manual_point_id(manual_payload(c)): manual_payload(c) for c in chunks}
    if not payloads or len(payloads) != len(chunks):
        raise ValueError("Empty or duplicate manual chunks")
    existing = {str(p.id): p for p in client.retrieve(collection, ids=list(payloads),
                                                     with_payload=True, with_vectors=False)}
    for point_id, point in existing.items():
        if point.payload != payloads[point_id]:
            raise ValueError("Existing manual point differs; refusing overwrite")
    missing = {i: p for i, p in payloads.items() if i not in existing}
    result = {"mode": "apply" if apply else "dry_run", "planned": len(payloads),
              "already_present": len(existing), "new_points": len(missing),
              "count_before": client.count(collection, exact=True).count,
              "points": [{"id": i, "name": p["name"], "item_code": p["item_code"],
                          "page": p["page"], "section": p["section"],
                          "source_url": p["source_url"], "source_sha256": p["source_sha256"],
                          "text_sha256": hashlib.sha256(p["text"].encode()).hexdigest()}
                         for i, p in payloads.items()]}
    if not apply:
        return result
    if missing and embedder is None:
        raise ValueError("An explicit embedding provider is required")
    for field in ("name", "item_code", "doc_type", "source_sha256"):
        if field not in info.payload_schema:
            client.create_payload_index(collection, field, field_schema=PayloadSchemaType.KEYWORD, wait=True)
        elif info.payload_schema[field].data_type.value != "keyword":
            raise ValueError("Incompatible payload index")
    points = []
    for point_id, payload in missing.items():
        vector = embedder(payload["text"])
        if len(vector) != 3072 or not all(math.isfinite(v) for v in vector):
            raise ValueError("Invalid manual embedding")
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))
    # One explicit upload; never retry the whole ingestion after an API error.
    if points:
        client.upsert(collection, points=points, wait=True)
    verified = client.retrieve(collection, ids=list(payloads), with_payload=True, with_vectors=False)
    if {str(p.id): p.payload for p in verified} != payloads:
        raise ValueError("Manual readback does not match prepared chunks")
    result["count_after"] = client.count(collection, exact=True).count
    result["verified"] = True
    return result
