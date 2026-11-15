"""Bounded real-provider smoke checks; no PostgreSQL writes or Qdrant uploads."""
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from app.rag.manuals import load_manifest, valid_manual_hit
from app.rag.retrieval import rag_service
from app.rag.embedding import embedding_service as embedding
from app.services import llm_service as llm
from app.orchestration import orchestrator
from app.db.executor import execute_query
from app.rag.vector_store import qdrant_client as q

assert json.loads((OUT / "ingestion.json").read_text(encoding="utf-8"))["status"] == "passed"
assert not (OUT / "live_checks.json").exists(), "This live attempt already ran"
PRIVATE = ROOT / ".cache/official_manuals" / (OUT.name + "_retrieved_chunks.json")
report = {"status": "running", "chat_attempts": 0, "chat_successes": 0, "chat_tokens": 0,
          "embedding_attempts": 0, "embedding_successes": 0, "embedding_tokens": 0,
          "automatic_retries": 0, "cases": [], "limits": {"chat": 20, "embedding": 6}}
raw_traces = []
trace = []
provider_errors = []
source_files = sorted({p for pattern in ("app/**/*.py", "scripts/*.py", "tests/**/*.py", "app/prompts/*.txt",
                    "data/model_manuals/*.json", "requirements*.txt", "main.py") for p in ROOT.glob(pattern)})
report["source_manifest"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in source_files}


def save():
    (OUT / "live_checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+"\n", encoding="utf-8")
    PRIVATE.write_text(json.dumps(raw_traces, ensure_ascii=False, indent=2, default=str)+"\n", encoding="utf-8")


def public_hit(hit):
    return {**{k:v for k,v in hit.items() if k != "text"},
            "text_sha256":hashlib.sha256(hit.get("text", "").encode()).hexdigest()}


try:
    db = execute_query("SELECT current_database(), current_setting('transaction_read_only'), count(*) FROM inventory_items")
    assert db["rows"][0] == ("inventory_ai_clean", "on", 1000)
    report["database"] = db
    docs = load_manifest()
    embedding.client = embedding._get_client().with_options(max_retries=0, timeout=45)
    llm.client = llm._get_client().with_options(max_retries=0, timeout=60)
    chat_create = llm.client.chat.completions.create
    embedding_create = embedding.client.embeddings.create
    def measured_chat(*args, **kwargs):
        assert report["chat_attempts"] < 20
        report["chat_attempts"] += 1
        save()
        try:
            response = chat_create(*args, **kwargs)
        except Exception as exc:
            provider_errors.append({"kind": "chat", "type": type(exc).__name__})
            raise
        report["chat_successes"] += 1
        report["chat_tokens"] += response.usage.total_tokens if response.usage else 0
        return response
    def measured_embedding(*args, **kwargs):
        assert report["embedding_attempts"] < 6
        report["embedding_attempts"] += 1
        save()
        try:
            response = embedding_create(*args, **kwargs)
        except Exception as exc:
            provider_errors.append({"kind": "embedding", "type": type(exc).__name__})
            raise
        report["embedding_successes"] += 1
        report["embedding_tokens"] += response.usage.total_tokens
        return response
    actual_model = rag_service.retrieve_by_model
    actual_semantic = rag_service.retrieve_semantic
    def traced_model(name, code, question, **kwargs):
        hits = actual_model(name, code, question, **kwargs)
        trace.append({"method": "exact_model", "name": name, "item_code": code,
                      "hits": [public_hit(h) for h in hits]})
        raw_traces.append({"question": question, "method": "exact_model", "hits": hits})
        doc = next(d for d in docs if (d["name"], d["item_code"]) == (name, code))
        assert hits and all(valid_manual_hit(h, doc) for h in hits)
        return hits
    def traced_semantic(question, **kwargs):
        hits = actual_semantic(question, **kwargs)
        trace.append({"method": "semantic_rag", "hits": [public_hit(h) for h in hits]})
        raw_traces.append({"question": question, "method": "semantic_rag", "hits": hits})
        return hits
    cases = [
        ("SQL", None, "How many inventory items are stored in the database?"),
        ("RAG", None, "How can I troubleshoot a docking station whose ports are not working?"),
        ("HYBRID", "P2422H", "Where is inventory item L-00502, what are its name and item_code, and how do I perform its monitor self-test?"),
        ("HYBRID", "HLL5200", "Where is inventory item L-00703, what are its name and item_code, and what should I do when the printer displays No Paper?"),
        ("HYBRID", "EBFH52", "Where is inventory item L-00901, what are its name and item_code, and how should I clean its projector air filter?"),
        ("HYBRID", "LAT5540", "Where is inventory item L-00001, what are its name and item_code, and how should I troubleshoot its battery?"),
    ]
    with patch.object(llm.client.chat.completions, "create", side_effect=measured_chat), \
         patch.object(embedding.client.embeddings, "create", side_effect=measured_embedding), \
         patch.object(rag_service, "retrieve_by_model", side_effect=traced_model), \
         patch.object(rag_service, "retrieve_semantic", side_effect=traced_semantic):
        for expected, code, question in cases:
            trace.clear()
            result = orchestrator.handle_question(question)
            if result.get("error"):
                result["error"] = {k:v for k,v in result["error"].items() if k != "detail"}
            case = {"expected_route": expected, "expected_item_code": code, "question": question,
                    "result": result, "retrieval": list(trace)}
            report["cases"].append(case)
            save()
            assert not provider_errors and result["ok"] and result["route"] == expected
            if expected == "SQL":
                assert result["result"]["rows"] == [(1000,)]
            elif expected == "RAG":
                assert any(s["source"] == "devices.txt" and s["name"] == "docking station" for s in result["sources"])
            elif code == "LAT5540":
                assert result["documentation_status"] == [{"name":"Dell Latitude 5540", "item_code":code, "status":"undocumented_model"}]
                assert not result["sources"] and not trace
            else:
                doc = next(d for d in docs if d["item_code"] == code)
                assert result["documentation_status"] == [{"name":doc["name"], "item_code":code, "status":"matched"}]
                assert all(s["name"] == doc["name"] and s["item_code"] == code and s["source_url"] == doc["source_url"]
                           and s["page"] in {p["page"] for p in doc["selections"]} for s in result["sources"])
                relevant_page = {"P2422H":69,"HLL5200":13,"EBFH52":166}[code]
                assert any(s["page"] == relevant_page for s in result["sources"])
            case["checks_passed"] = True
            save()
            print(json.dumps({"route":expected,"item_code":code,"passed":True}), flush=True)
        before_calls = (report["chat_attempts"], report["embedding_attempts"])
        trace.clear()
        invalid = rag_service.answer_hybrid_details("Documentation for this model?", [],
            {"columns":["name","item_code"], "rows":[["Dell P2422H","HLL5200"]]})
        assert invalid["documentation_status"][0]["status"] == "identifier_conflict"
        assert invalid["sources"] == [] and not trace
        assert before_calls == (report["chat_attempts"], report["embedding_attempts"])
        report["negative_pair"] = {"input_origin":"deliberately invalid test fixture; no database mutation",
            "name":"Dell P2422H","item_code":"HLL5200","result":invalid,"checks_passed":True}
    report["status"] = "passed"
except Exception as exc:
    report.update(status="stopped_on_error",error_type=type(exc).__name__)
finally:
    report["provider_errors"] = provider_errors
    report["qdrant_points"] = q.client.count("devices", exact=True).count
    save()
    q.client.close()
print(json.dumps({k:report[k] for k in ("status","chat_attempts","chat_successes","embedding_attempts",
                                      "embedding_successes","qdrant_points","provider_errors")}), flush=True)
raise SystemExit(0 if report["status"] == "passed" else 1)
