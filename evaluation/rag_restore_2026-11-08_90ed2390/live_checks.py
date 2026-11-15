"""Bounded live read-only smoke checks after successful ingestion; no reindexing."""
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
from app.rag.vector_store import qdrant_client as q
from app.rag.embedding import embedding_service as emb
from app.services import llm_service as llm
from app.rag.retrieval import retriever, rag_service
from app.orchestration import orchestrator
from app.db.executor import execute_query
from qdrant_client.models import Filter, FieldCondition, MatchValue

assert json.loads((OUT / "ingestion.json").read_text(encoding="utf-8"))["status"] == "succeeded"
assert not (OUT / "live_checks.json").exists(), "Smoke run already recorded"
report = {"date": "2026-11-08", "chat_requests": 0, "chat_succeeded": 0, "chat_tokens": 0,
          "embedding_requests": 0, "embedding_succeeded": 0, "embedding_tokens": 0,
          "limits": {"chat_requests": 8, "embedding_requests": 4},
          "live_calls": True, "automatic_retries": 0, "routes": []}
provider_errors = []
vectors = []
retrieval_trace = []
current_phase = "setup"

def save():
    (OUT / "live_checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+"\n",encoding="utf-8")

def safe_error(exc):
    seen=set()
    chain=[]
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        code=getattr(exc,"code",None)
        code=code if code in {"invalid_api_key","insufficient_quota","rate_limit_exceeded","model_not_found",
                             "unsupported_parameter","unsupported_value"} else None
        chain.append({"type":type(exc).__name__,"http_status":getattr(exc,"status_code",None),"code":code})
        exc=exc.__cause__ or exc.__context__
    return chain

try:
    db=execute_query("SELECT current_database() AS database, current_setting('transaction_read_only') AS read_only, count(*) AS records FROM inventory_items")
    assert db["rows"][0] == ("inventory_ai_clean","on",1000)
    report["postgres"]=db
    sample=execute_query("SELECT inventory_number, name, location FROM inventory_items WHERE inventory_number = 'L-00001'")
    report["reference_inventory_record"]=sample
    all_names=execute_query("SELECT DISTINCT name FROM inventory_items ORDER BY name")
    points,_=q.client.scroll("devices",limit=100,with_payload=True,with_vectors=False)
    assert len(points)==40
    knowledge_names={p.payload["name"] for p in points}
    report["hybrid_name_analysis"]={"clean_distinct_names":len(all_names["rows"]),
        "knowledge_names":sorted(knowledge_names),
        "exact_name_intersection":sorted({row[0].strip().lower() for row in all_names["rows"]}&knowledge_names)}

    emb.client=emb._get_client().with_options(max_retries=0,timeout=30)
    llm.client=llm._get_client().with_options(max_retries=0,timeout=45)
    original_embedding=emb.client.embeddings.create
    original_chat=llm.client.chat.completions.create

    def measured_embedding(*args,**kwargs):
        assert report["embedding_requests"] < 4, "Embedding budget reached"
        report["embedding_requests"]+=1
        try:
            response=original_embedding(*args,**kwargs)
        except Exception as exc:
            provider_errors.append({"phase":current_phase,"kind":"embedding","error":safe_error(exc)})
            raise
        report["embedding_succeeded"]+=1
        report["embedding_tokens"]+=response.usage.total_tokens
        vectors.append(response.data[0].embedding)
        return response

    def measured_chat(*args,**kwargs):
        assert report["chat_requests"] < 8, "Chat budget reached"
        report["chat_requests"]+=1
        try:
            response=original_chat(*args,**kwargs)
        except Exception as exc:
            provider_errors.append({"phase":current_phase,"kind":"chat","model":kwargs.get("model"),"error":safe_error(exc)})
            raise
        report["chat_succeeded"]+=1
        if response.usage:report["chat_tokens"]+=response.usage.total_tokens
        return response

    original_semantic=rag_service.retrieve_semantic
    original_by_name=rag_service.retrieve_by_name
    def traced_semantic(*args,**kwargs):
        hits=original_semantic(*args,**kwargs)
        retrieval_trace.append({"method":"semantic_fallback_or_rag","names":[h.get("name") for h in hits],"hits":len(hits)})
        return hits
    def traced_by_name(name,*args,**kwargs):
        hits=original_by_name(name,*args,**kwargs)
        retrieval_trace.append({"method":"name_filter","name":name,"hits":len(hits)})
        return hits

    with patch.object(emb.client.embeddings,"create",side_effect=measured_embedding), \
         patch.object(llm.client.chat.completions,"create",side_effect=measured_chat), \
         patch.object(rag_service,"retrieve_semantic",side_effect=traced_semantic), \
         patch.object(rag_service,"retrieve_by_name",side_effect=traced_by_name):
        current_phase="semantic_retrieval"
        hits=retriever.retrieve_semantic("My printer is not responding. What should I check?",limit=3)
        report["semantic_search"]={"question":"My printer is not responding. What should I check?",
            "hits":[{k:h.get(k) for k in ("name","section","source","doc_type","score")} for h in hits],
            "printer_rank_one":bool(hits and hits[0].get("name")=="printer")}
        assert report["semantic_search"]["printer_rank_one"]
        full_name=sample["rows"][0][1].strip().lower()
        filtered=q.client.query_points("devices",query=vectors[0],
            query_filter=Filter(must=[FieldCondition(key="name",match=MatchValue(value=full_name))]),
            limit=3,with_payload=False).points
        report["hybrid_name_analysis"]["live_full_model_filter"]={"name":full_name,"hits":len(filtered)}
        save()
        print(json.dumps({"semantic_retrieval":"passed","top_name":hits[0].get("name"),"full_model_filter_hits":len(filtered)}),flush=True)

        questions=[
            ("SQL","How many inventory items are stored in the database?"),
            ("RAG","How can I troubleshoot a printer that is not responding?"),
            ("HYBRID","Where is inventory item L-00001 located, what is its name, and how should I troubleshoot the laptop if it will not turn on?")
        ]
        for expected,question in questions:
            current_phase=expected
            retrieval_trace.clear()
            if provider_errors:
                report["routes"].append({"expected_route":expected,"status":"not_run_after_provider_error"})
                continue
            answer=orchestrator.handle_question(question)
            error=answer.get("error")
            if error:answer["error"]={k:v for k,v in error.items() if k in ("code","title","message")}
            report["routes"].append({"expected_route":expected,"question":question,
                "route_correct":answer.get("route")==expected,"result":answer,"retrieval_trace":list(retrieval_trace)})
            save()
            print(json.dumps({"expected_route":expected,"actual_route":answer.get("route"),"ok":answer.get("ok"),
                              "chat_requests":report["chat_requests"],"embedding_requests":report["embedding_requests"]}),flush=True)
    report["provider_errors"]=provider_errors
    report["status"]="passed" if not provider_errors and all(r.get("route_correct") and r.get("result",{}).get("ok")
        for r in report["routes"]) else "partial_or_failed"
except Exception as exc:
    report["status"]="stopped_on_error"
    report["error_phase"]=current_phase
    report["error_chain"]=safe_error(exc)
    report["provider_errors"]=provider_errors
finally:
    report["points_after_checks"]=q.client.count("devices",exact=True).count
    save()
    q.client.close()
print(json.dumps({k:report[k] for k in ("status","chat_requests","chat_succeeded","embedding_requests","embedding_succeeded","provider_errors","points_after_checks")}),flush=True)
