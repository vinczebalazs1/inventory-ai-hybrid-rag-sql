"""Read-only clean-DB integration; AI and Qdrant are explicit test substitutes."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")

import httpx
import requests
from qdrant_client import QdrantClient


def forbid_http(*args, **kwargs):
    raise AssertionError("External HTTP is forbidden; AI calls must be substituted")


def run():
    from app.db.connection import get_connection
    from app.db.executor import execute_query
    from app.record_matching import repository as repository_module
    from app.record_matching.repository import InventoryRepository
    from app.record_matching.config import MatchingSettings
    from app.record_matching.reconciliation_service import reconcile_document
    from app.test_data.artifacts import read_bundle, source_hashes
    from app.test_data.documents import read_ground_truth
    from app.test_data.evaluation import processing_input, assess
    from app.document_processing import processing_service
    from app.document_processing.docling_parser import parse_document
    from app.document_processing.config import Settings
    from app.services import llm_service

    results = {"date": "2026-11-08", "live_llm_calls": 0, "live_qdrant_writes": 0,
               "scope": "Real configured PostgreSQL and Docling; stubbed LLM/embedding; in-memory Qdrant"}
    status = execute_query("SELECT current_database() AS database, current_user AS username, "
                           "current_setting('transaction_read_only') AS read_only, "
                           "count(*) AS records FROM inventory_items")
    database, username, read_only, count = status["rows"][0]
    assert (database, read_only, count) == ("inventory_ai_clean", "on", 1000)
    assert repository_module.get_connection is get_connection
    results["configured_sql_connection"] = {"database": database, "username": username,
        "read_only": read_only, "records": count, "same_connection_function_for_matching": True}

    observations = []

    class ObservedRepository(InventoryRepository):
        @contextlib.contextmanager
        def _transaction(self, settings):
            with super()._transaction(settings) as cursor:
                cursor.execute("SELECT current_database(), current_setting('transaction_read_only')")
                observed = cursor.fetchone()
                assert observed == ("inventory_ai_clean", "on")
                observations.append(observed)
                yield cursor

    rows, config, manifest = read_bundle(ROOT / "data/synthetic")
    truth = read_ground_truth(ROOT / "data/synthetic", manifest)
    repo = ObservedRepository()
    cases = []
    for case in truth["scenarios"]:
        actual = reconcile_document(processing_input(case), repository=repo, settings=MatchingSettings())
        assert actual.match_status.value != "ERROR"
        checked = assess(case, actual)
        checked["fuzzy_attempted"] = actual.search_metadata.fuzzy_search.attempted
        checked["candidate_count"] = len(actual.candidates)
        cases.append(checked)
    old = json.loads((ROOT / "evaluation/clean_inventory/matching_postgres.json").read_text())
    compared = ("document_id", "actual_category", "actual_inventory_number", "actual_differences",
                "actual_actions", "review_required", "checks")
    assert [{k:c[k] for k in compared} for c in cases] == [{k:c[k] for k in compared} for c in old["cases"]]
    assert any(c["fuzzy_attempted"] and c["candidate_count"] for c in cases)
    results["live_matching_known_fields"] = {"reference_passed": sum(c["passed"] for c in cases),
        "total": len(cases), "same_decisions_as_saved_report": True, "cases": cases,
        "observed_transactions": observations}

    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    converter = DocumentConverter(allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=PdfPipelineOptions(
            artifacts_path=Settings.from_env().artifacts_path))})
    documents = []
    last_processed = None
    for case in truth["scenarios"][:2]:
        for suffix in ("docx", "pdf"):
            path = ROOT / "data/synthetic/documents" / (case["document_id"] + "." + suffix)
            fields = case["expected_fields"]
            stub = Mock(side_effect=[json.dumps({"document_type": "inventory", "fields": [
                {"label": f["label"], "value": f["raw"], "evidence": f"{f['label']}: {f['raw']}"}
                for f in fields]}), json.dumps({"assignments": [
                    {"index": i, "target_field": f["field"]} for i, f in enumerate(fields)]})])
            with patch.object(llm_service, "ask_llm", stub), patch.object(processing_service,
                    "parse_document", lambda data, name, **kwargs: parse_document(data, name,
                        converter=converter, **kwargs)):
                processed = processing_service.process_document(path.read_bytes(), path.name)
            actual = reconcile_document(processed, repository=repo, settings=MatchingSettings())
            assert stub.call_count == 2 and assess(case, actual)["passed"]
            documents.append({"file": path.name, "real_docling": True, "stub_llm_calls": stub.call_count,
                "database": "inventory_ai_clean", "status": actual.match_status.value,
                "differences": [c.field for c in actual.field_comparisons if c.status.value == "DIFFERENT"],
                "actions": [a.action_type.value for a in actual.suggested_actions]})
            last_processed = processed
    results["document_processing"] = documents

    memory_client = QdrantClient(location=":memory:")
    # The production REST backend validates dict points through PointsList.
    # QdrantLocal skips that REST conversion, so reproduce it in the test double.
    from qdrant_client.http.models import PointsList
    original_upsert = memory_client.upsert

    def local_upsert_with_rest_validation(**kwargs):
        kwargs["points"] = PointsList(points=kwargs["points"]).points
        return original_upsert(**kwargs)

    memory_client.upsert = local_upsert_with_rest_validation
    with patch("qdrant_client.QdrantClient", return_value=memory_client):
        from app.rag.vector_store import qdrant_client as store
        from app.rag.ingestion import ingestion_service
        from app.rag.retrieval import retriever, rag_service
        from app.orchestration import orchestrator
        from app.services import routing_service, sql_generation_service, answer_service
    vector = [0.1] * 3072
    with patch.object(ingestion_service, "embed_text", return_value=vector), \
         patch.object(retriever, "embed_text", return_value=vector):
        uploaded = {}
        for name, contents in (("audit_manual.txt", b"Laptop usage: press the power button."),
                ("audit_D01.pdf", (ROOT / "data/synthetic/documents/D01.pdf").read_bytes())):
            uploaded[name] = ingestion_service.ingest_uploaded_document(name, contents)
            assert uploaded[name] > 0
        assert retriever.retrieve_semantic("Laptop usage")
        assert retriever.retrieve_by_name("audit_manual.txt", "Laptop usage")
        results["rag_upload"] = {"destination": "in-memory Qdrant only", "chunks": uploaded,
                                 "semantic_and_name_filtered_retrieval": True,
                                 "adapter": "PointsList validation, matching the production REST backend"}
        routes = []
        for route in ("SQL", "RAG", "HYBRID"):
            with patch.object(routing_service, "ask_llm", return_value=route), \
                 patch.object(sql_generation_service, "ask_llm", return_value=
                     "SELECT inventory_number, name, location FROM inventory_items ORDER BY inventory_number LIMIT 1"), \
                 patch.object(answer_service, "ask_llm", return_value="Stubbed SQL answer"), \
                 patch.object(rag_service, "ask_llm", return_value="Stubbed documented answer"):
                answer = orchestrator.handle_question("Where is the laptop and how is it used?")
            assert answer["ok"] and answer["route"] == route
            if route != "RAG": assert answer["result"]["rows"][0][0] == "L-00001"
            if route != "SQL": assert answer["sources"]
            routes.append({"route": route, "ok": answer["ok"],
                           "sql_rows": answer["result"]["row_count"], "sources": len(answer["sources"]),
                           "ai": "stubbed", "qdrant": "in-memory", "postgres": "live clean when used"})
        results["old_routes"] = routes

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "app/web/simple_server.py")).run(timeout=60)
        assert not at.exception
        at.session_state["document_preview"] = last_processed
        at.run(timeout=60)
        at.button(key="reconcile_document").click().run(timeout=60)
        assert not at.exception
        actual = at.session_state["document_reconciliation"]
        assert actual.match_status.value == "EXACT_MATCH"
        assert any(c.field == "location" and c.status.value == "DIFFERENT" for c in actual.field_comparisons)
        assert any(a.action_type.value == "UPDATE_CANDIDATE" for a in actual.suggested_actions)
        assert len(at.dataframe) >= 3
        results["streamlit"] = {"real_entry_point": "app/web/simple_server.py", "exceptions": 0,
            "real_reconciliation_button": True, "status": actual.match_status.value,
            "location_difference_and_update_proposal": True, "rendered_dataframes": len(at.dataframe),
            "qdrant": "in-memory", "llm": "stubbed earlier document processing"}
    memory_client.close()
    results["implementation_sha256"], results["source_manifest"] = source_hashes()
    results["status"] = "passed_with_explicit_substitutions"
    return results


if __name__ == "__main__":
    attempt = OUT / "functional_attempt_02"
    attempt.mkdir(exist_ok=False)
    with (attempt / "functional.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), \
             patch.object(httpx.Client, "send", forbid_http), \
             patch.object(httpx.AsyncClient, "send", forbid_http), \
             patch.object(requests.Session, "request", forbid_http):
            try:
                result = run()
            except Exception as exc:
                import traceback
                result = {"status": "failed", "error_type": type(exc).__name__,
                          "stack": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                                    for f in traceback.extract_tb(exc.__traceback__)]}
    (attempt / "functional_checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k in ("status", "error_type", "stack", "streamlit", "document_processing")}))
    raise SystemExit(0 if result["status"] == "passed_with_explicit_substitutions" else 1)
