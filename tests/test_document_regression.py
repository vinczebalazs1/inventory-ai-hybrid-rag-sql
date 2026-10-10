"""Offline checks of the existing routes and RAG upload contract."""
from unittest.mock import Mock

import pytest

from app.orchestration import orchestrator
from app.rag.ingestion import ingestion_service
from app.services import routing_service


@pytest.mark.parametrize("route", ["SQL", "RAG", "HYBRID"])
def test_existing_routes(monkeypatch, route):
    monkeypatch.setattr(routing_service, "ask_llm", Mock(return_value=route))
    assert routing_service.route_query("Where is the laptop?") == route
    monkeypatch.setattr(orchestrator, "route_query", Mock(return_value=route))
    sql = Mock(return_value="SELECT name FROM inventory_items")
    execute = Mock(return_value={"columns": ["name"], "rows": [["Laptop"]], "row_count": 1})
    monkeypatch.setattr(orchestrator, "generate_sql", sql)
    monkeypatch.setattr(orchestrator, "execute_query", execute)
    monkeypatch.setattr(orchestrator, "generate_natural_answer", Mock(return_value="SQL answer"))
    monkeypatch.setattr(orchestrator, "answer_rag_details", Mock(return_value={"answer": "RAG answer", "sources": []}))
    hybrid = Mock(return_value={"answer": "Hybrid answer", "sources": []})
    monkeypatch.setattr(orchestrator, "answer_hybrid_details", hybrid)
    result = orchestrator.handle_question("Where is the laptop?")
    assert result["ok"] and result["route"] == route
    if route == "RAG":
        execute.assert_not_called()
    else:
        assert execute.call_args.args[0].startswith("SELECT")
        assert "LIMIT" in execute.call_args.args[0]
    if route == "HYBRID":
        assert hybrid.call_args.args[1] == ["laptop"]


def test_existing_rag_upload(monkeypatch):
    initialize = Mock()
    upsert = Mock()
    monkeypatch.setattr(ingestion_service, "init_collection", initialize)
    monkeypatch.setattr(ingestion_service, "embed_text", Mock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(ingestion_service, "upsert_points", upsert)
    count = ingestion_service.ingest_uploaded_document("manual.txt", b"Laptop usage: turn on the power.")
    assert count == 1
    assert upsert.call_args.args[0][0]["payload"]["source"] == "manual.txt"
    initialize.assert_called_once()
