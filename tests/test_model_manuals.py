"""Model isolation, reviewed provenance, non-destructive/idempotent ingestion."""
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid5, NAMESPACE_URL

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

from app.rag import manuals
from app.rag.models.rag_models import RagChunk
from app.rag.retrieval import rag_service, retriever

VECTOR = [1.0] + [0.0] * 3071


def sample_chunks():
    chunks = []
    for doc in manuals.load_manifest():
        selection = doc["selections"][0]
        chunks.append(RagChunk(name=doc["name"], item_code=doc["item_code"],
            text="Offline fixture, not manufacturer text.", section=selection["section"] + "/chunk-1",
            source=doc["file"], doc_type=manuals.MANUAL_TYPE, source_url=doc["source_url"],
            source_sha256=doc["sha256"], page=selection["page"]))
    return chunks


@pytest.fixture
def store():
    client = QdrantClient(location=":memory:")
    client.create_collection("devices", vectors_config=VectorParams(size=3072, distance=Distance.COSINE))
    client.upsert("devices", points=[PointStruct(id=str(uuid5(NAMESPACE_URL, f"legacy/{i}")),
        vector=VECTOR, payload={"name": "printer", "text": f"Generic {i}", "source": "devices.txt",
                                "section": "usage", "doc_type": "device_txt"}) for i in range(40)])
    yield client
    client.close()


def snapshot(client):
    points, _ = client.scroll("devices", limit=100, with_payload=True, with_vectors=True)
    return {str(p.id): (p.payload, p.vector) for p in points}


@pytest.mark.filterwarnings("ignore:Payload indexes have no effect")
def test_dry_run_idempotence_and_all_legacy_points_preserved(store):
    before = snapshot(store)
    embedding = Mock(return_value=VECTOR)
    chunks = sample_chunks()
    dry = manuals.index_manual_chunks(store, "devices", chunks, embedder=embedding)
    assert dry["new_points"] == 3 and snapshot(store) == before
    embedding.assert_not_called()
    applied = manuals.index_manual_chunks(store, "devices", chunks, apply=True, embedder=embedding)
    assert applied["count_after"] == 43 and embedding.call_count == 3
    after = snapshot(store)
    assert {i: after[i] for i in before} == before
    again = manuals.index_manual_chunks(store, "devices", chunks, apply=True)
    assert again["new_points"] == 0 and again["already_present"] == 3
    assert snapshot(store) == after


@pytest.mark.filterwarnings("ignore:Payload indexes have no effect")
def test_embedding_failure_does_not_retry_or_upload_partial_batch(store):
    before = snapshot(store)
    embedding = Mock(side_effect=[VECTOR, RuntimeError("offline provider failure")])
    with pytest.raises(RuntimeError):
        manuals.index_manual_chunks(store, "devices", sample_chunks(), apply=True, embedder=embedding)
    assert embedding.call_count == 2 and snapshot(store) == before


def test_existing_point_mismatch_refuses_overwrite(store):
    chunks = sample_chunks()
    payload = manuals.manual_payload(chunks[0])
    point_id = manuals.manual_point_id(payload)
    store.upsert("devices", points=[PointStruct(id=point_id, vector=VECTOR,
                                                payload={**payload, "text": "changed"})])
    before = snapshot(store)
    with pytest.raises(ValueError, match="refusing overwrite"):
        manuals.index_manual_chunks(store, "devices", chunks, apply=True, embedder=Mock())
    assert snapshot(store) == before


@pytest.fixture
def indexed(store, monkeypatch):
    chunks = sample_chunks()
    store.upsert("devices", points=[PointStruct(id=manuals.manual_point_id(manuals.manual_payload(c)),
        vector=VECTOR, payload=manuals.manual_payload(c)) for c in chunks])
    def search(vector, query_filter=None, limit=3):
        return store.query_points("devices", query=vector, query_filter=query_filter, limit=limit).points
    monkeypatch.setattr(retriever, "search", search)
    monkeypatch.setattr(retriever, "embed_text", Mock(return_value=VECTOR))
    monkeypatch.setattr(rag_service, "embed_text", Mock(return_value=VECTOR))
    return store


@pytest.mark.parametrize("doc", manuals.load_manifest(), ids=lambda d: d["item_code"])
def test_exact_model_filter_and_hybrid_sources(indexed, monkeypatch, doc):
    llm = Mock(return_value="Offline grounded answer")
    monkeypatch.setattr(rag_service, "ask_llm", llm)
    monkeypatch.setattr(rag_service, "retrieve_semantic", Mock(side_effect=AssertionError("No fallback")))
    sql = {"columns": ["name", "item_code", "location"], "rows": [[doc["name"], doc["item_code"], "LIB"]]}
    result = rag_service.answer_hybrid_details("How to maintain it?", ["untrusted name"], sql)
    assert result["documentation_status"][0]["status"] == "matched"
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert (source["name"], source["item_code"], source["source_url"], source["page"]) == (
        doc["name"], doc["item_code"], doc["source_url"], doc["selections"][0]["page"])
    assert source["source_kind"] == "manufacturer" and source["source_sha256"] == doc["sha256"]
    assert "untrusted name" not in llm.call_args.args[0]


@pytest.mark.parametrize("name,code,status", [
    ("Dell Latitude 5540", "LAT5540", "undocumented_model"),
    ("Dell P2422H", "HLL5200", "identifier_conflict"),
    ("Brother HL-L5200DW", "P2422H", "identifier_conflict"),
    ("dell p2422h", "P2422H", "identifier_conflict"),
])
def test_negative_identity_has_no_api_or_foreign_manual(monkeypatch, name, code, status):
    no_call = Mock(side_effect=AssertionError("No API/retrieval for invalid identity"))
    for attr in ("embed_text", "ask_llm", "retrieve_by_model", "retrieve_semantic"):
        monkeypatch.setattr(rag_service, attr, no_call)
    result = rag_service.answer_hybrid_details("Technical question", [name],
        {"columns": ["name", "item_code"], "rows": [[name, code]]})
    assert result["sources"] == []
    assert result["documentation_status"][0]["status"] == status
    assert name in result["answer"]
    no_call.assert_not_called()


def test_partial_multi_model_coverage_is_reported(indexed, monkeypatch):
    monkeypatch.setattr(rag_service, "ask_llm", Mock(return_value="Only documented model advice."))
    result = rag_service.answer_hybrid_details("Maintain both", [], {"columns": ["name", "item_code"],
        "rows": [["Dell P2422H", "P2422H"], ["Dell Latitude 5540", "LAT5540"]]})
    assert {s["status"] for s in result["documentation_status"]} == {"matched", "undocumented_model"}
    assert all(s["item_code"] == "P2422H" for s in result["sources"])
    assert "Dell Latitude 5540" in result["answer"]
    assert rag_service.embed_text.call_count == 1


def test_missing_identity_is_not_inferred_from_question(monkeypatch):
    llm = Mock(side_effect=AssertionError("No LLM needed"))
    monkeypatch.setattr(rag_service, "ask_llm", llm)
    result = rag_service.answer_hybrid_details("Dell P2422H P2422H", ["Dell P2422H"],
                                             {"columns": ["count"], "rows": [[67]]})
    assert result["documentation_status"][0]["status"] == "missing_model_identity"
    assert result["sources"] == []


def test_known_but_not_indexed_model_is_explicit(store, monkeypatch):
    monkeypatch.setattr(rag_service, "embed_text", Mock(return_value=VECTOR))
    monkeypatch.setattr(rag_service, "retrieve_by_model", Mock(return_value=[]))
    result = rag_service.answer_hybrid_details("help", [], {"columns": ["name", "item_code"],
                                             "rows": [["Dell P2422H", "P2422H"]]})
    assert result["documentation_status"][0]["status"] == "not_indexed"


@pytest.mark.parametrize("field,value", [("page", 999), ("source_url", "https://example.invalid"),
                                        ("source_sha256", "0"*64), ("item_code", "other")])
def test_hit_provenance_is_validated(field, value):
    doc = manuals.load_manifest()[0]
    payload = manuals.manual_payload(sample_chunks()[0])
    assert manuals.valid_manual_hit(payload, doc)
    payload[field] = value
    assert not manuals.valid_manual_hit(payload, doc)


def test_generic_knowledge_still_retrievable_and_labelled(indexed):
    hits = retriever.retrieve_by_name("Printer", "usage")
    assert hits and all(h["source"] == "devices.txt" for h in hits)
    assert all(s["source_kind"] == "general" for s in rag_service.build_sources(hits))


def test_manual_selection_fails_closed():
    for text in ("no anchor", "START once START twice"):
        with pytest.raises(ValueError):
            manuals.selected_text(text, {"start": "START"})
    assert manuals.selected_text("other START relevant END excluded", {"start": "START", "end": "END"}) == "START relevant"


def test_reviewed_pdfs_offline_if_available():
    docs = manuals.load_manifest()
    if not all((manuals.PDF_DIRECTORY / d["file"]).exists() for d in docs):
        pytest.skip("Manufacturer PDFs deliberately not distributed with the repository")
    chunks = manuals.prepare_chunks(docs)
    assert len(chunks) == 11
    assert {c.item_code for c in chunks} == {"P2422H", "HLL5200", "EBFH52"}
    epson = "\n".join(c.text for c in chunks if c.item_code == "EBFH52")
    brother = "\n".join(c.text for c in chunks if c.item_code == "HLL5200")
    assert "10,000" not in epson and "6,000" not in epson
    assert "TN-" not in brother and "No Paper Fed T2" not in brother
    modified = deepcopy(docs)
    modified[0]["sha256"] = "0"*64
    with pytest.raises(ValueError, match="hash"):
        manuals.prepare_chunks(modified)
