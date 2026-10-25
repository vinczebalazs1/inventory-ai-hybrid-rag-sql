"""Real disposable PostgreSQL. No tests connect to the developer's DB_* target."""
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from unittest.mock import patch, Mock
import json
import os

import psycopg2
import pytest

from test_matching_postgres import isolated_postgres  # Reuse existing opt-in cluster lifecycle.
from app.test_data.artifacts import ROOT, dataset_hash, read_bundle, source_hashes, write_json
from app.test_data.database import (TARGET, CleanDatabaseError, ConnectionConfig, create_database,
    load_dataset, migrate, require_database, schema_report, verify_dataset)
from app.test_data.documents import read_ground_truth
from app.test_data.evaluation import assess, evaluate, processing_input
from app.test_data.generator import generate
from app.test_data.models import GenerationConfig
from app.record_matching.config import MatchingSettings
from app.record_matching.repository import InventoryRepository
from app.record_matching.reconciliation_service import reconcile_document


@pytest.fixture(scope="module")
def clean_environment(isolated_postgres, tmp_path_factory):
    config = ConnectionConfig(TARGET, "matching_test", "unused", "127.0.0.1", 5432)
    admin = isolated_postgres()
    params = admin.get_dsn_parameters()
    admin.close()
    params = {key: params[key] for key in ("host", "port", "user")}
    def connect(dbname=TARGET):
        return psycopg2.connect(**params, dbname=dbname, connect_timeout=5)
    # A sentinel old inventory exists only inside this disposable cluster.
    conn = connect("postgres")
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE DATABASE inventory")
    finally:
        conn.close()
    with connect("inventory") as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE public.untouched (value text)")
            cur.execute("INSERT INTO public.untouched VALUES ('KEEP-ORIGINAL')")
    conn.close()
    dry = create_database(config, connection_factory=isolated_postgres)
    assert dry["status"] == "would_create"
    created = create_database(config, apply=True, confirm_db=TARGET, connection_factory=isolated_postgres)
    assert created["status"] == "created"
    assert create_database(config, apply=True, confirm_db=TARGET, connection_factory=isolated_postgres)["status"] == "already_exists"
    inspection = migrate(config, connection_factory=connect)
    assert not inspection["schema_compatible"] and inspection["dry_run"]
    first = migrate(config, apply=True, confirm_db=TARGET, connection_factory=connect)
    second = migrate(config, apply=True, confirm_db=TARGET, connection_factory=connect)
    assert first["constraints_verified"] and second["constraints_verified"]
    rows, generation, manifest = read_bundle(ROOT / "data/synthetic")
    dry = load_dataset(config, rows, generation, connection_factory=connect)
    assert dry["status"] == "would_load" and dry["record_count"] == 0
    import app.test_data.database as module
    actual_insert = module.execute_values
    calls = []
    def fail_after_first_batch(cursor, query, batch, **kwargs):
        calls.append(len(batch))
        if len(calls) == 2:
            raise RuntimeError("Simulated failure after 250 inserts")
        return actual_insert(cursor, query, batch, **kwargs)
    with patch.object(module, "execute_values", side_effect=fail_after_first_batch):
        with pytest.raises(RuntimeError):
            load_dataset(config, rows, generation, apply=True, confirm_db=TARGET, connection_factory=connect)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.inventory_items")
            assert cur.fetchone()[0] == 0
    conn.close()
    loaded = load_dataset(config, rows, generation, apply=True, confirm_db=TARGET, connection_factory=connect)
    repeated = load_dataset(config, rows, generation, apply=True, confirm_db=TARGET, connection_factory=connect)
    assert loaded["status"] == "loaded" and repeated["status"] == "already_loaded"
    verified = verify_dataset(config, rows, generation, connection_factory=connect)
    assert verified["validation_passed"]
    truth = read_ground_truth(ROOT / "data/synthetic", manifest)
    report = {"environment": "isolated temporary PostgreSQL; never user DB_*", "load": loaded,
              "second_load": repeated, "verification": verified, "rollback_verified": calls == [250, 250]}
    yield config, connect, rows, generation, truth, report
    with connect("inventory") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM public.untouched")
            assert cur.fetchall() == [("KEEP-ORIGINAL",)]
    conn.close()
    report["old_database_sentinel_unchanged"] = True
    report["implementation_sha256"], report["source_manifest"] = source_hashes()
    path = Path(os.getenv("CLEAN_INVENTORY_REPORT_DIR", str(tmp_path_factory.mktemp("clean_reports"))))
    write_json(path / "postgres_verification.json", report)


def test_real_loader_lifecycle_dry_run_rollback_idempotence_and_verification(clean_environment):
    _, _, _, _, _, report = clean_environment
    assert report["rollback_verified"]
    assert report["verification"]["record_count"] == 1000
    assert report["verification"]["constraints_verified"] and report["verification"]["dataset_hash_verified"]


@pytest.mark.parametrize("field,value,exception", [
    ("inventory_number", "L-00001", psycopg2.errors.UniqueViolation),
    ("inventory_number", None, psycopg2.errors.NotNullViolation),
    ("inventory_number", "", psycopg2.errors.CheckViolation),
    ("inventory_number", " \t\n", psycopg2.errors.CheckViolation),
    ("inventory_number", "L-1", psycopg2.errors.CheckViolation),
    ("quantity", 2, psycopg2.errors.CheckViolation),
    ("quantity", None, psycopg2.errors.NotNullViolation),
    ("name", " \t", psycopg2.errors.CheckViolation),
    ("name", None, psycopg2.errors.NotNullViolation),
    ("purchase_value", -1, psycopg2.errors.CheckViolation),
    ("depreciation", -1, psycopg2.errors.CheckViolation),
    ("current_value", -1, psycopg2.errors.CheckViolation),
    ("currency", "forint", psycopg2.errors.CheckViolation),
])
def test_actual_postgres_constraints_reject_invalid_writes(clean_environment, field, value, exception):
    from psycopg2 import sql
    _, connect, _, _, _, _ = clean_environment
    connection = connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(exception):
                cursor.execute(sql.SQL("UPDATE public.inventory_items SET {} = %s WHERE inventory_number = 'L-00002'").format(
                    sql.Identifier(field)), (value,))
    finally:
        connection.rollback()
        connection.close()


def test_mismatching_dataset_refuses_overwrite(clean_environment):
    config, connect, rows, generation, _, _ = clean_environment
    different = GenerationConfig(seed=43)
    with pytest.raises(CleanDatabaseError, match="nem üres"):
        load_dataset(config, generate(different), different, apply=True, confirm_db=TARGET, connection_factory=connect)
    assert verify_dataset(config, rows, generation, connection_factory=connect)["validation_passed"]


def test_actual_wrong_database_blocks_loader_and_both_migrations(clean_environment):
    config, connect, rows, generation, _, _ = clean_environment
    with pytest.raises(CleanDatabaseError):
        load_dataset(config, rows, generation, apply=True, confirm_db=TARGET, connection_factory=lambda: connect("inventory"))
    for name in ("001_create_inventory_items.sql", "002_add_inventory_constraints.sql"):
        connection = connect("inventory")
        try:
            with connection.cursor() as cursor:
                with pytest.raises(psycopg2.errors.RaiseException, match="expected inventory_ai_clean"):
                    cursor.execute((ROOT / "migrations/clean" / name).read_text(encoding="utf-8"))
        finally:
            connection.rollback()
            connection.close()


@pytest.mark.parametrize("change", [
    "ALTER TABLE public.inventory_items DROP CONSTRAINT clean_quantity_one",
    "ALTER TABLE public.inventory_items DROP CONSTRAINT clean_quantity_one; ALTER TABLE public.inventory_items ADD CONSTRAINT clean_quantity_one CHECK (quantity >= 1)",
    "ALTER TABLE public.inventory_items ADD extra_id integer",
    "ALTER TABLE public.inventory_items ALTER COLUMN inventory_number DROP NOT NULL",
    "ALTER TABLE public.inventory_items DROP CONSTRAINT clean_inventory_unique",
    "COMMENT ON TABLE public.inventory_items IS 'unmanaged'",
    "ALTER TABLE public.inventory_items ENABLE ROW LEVEL SECURITY",
])
def test_verifier_detects_schema_drift_by_definition(clean_environment, change):
    _, connect, _, _, _, _ = clean_environment
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(change)
            assert not schema_report(cursor)["constraints_verified"]
    finally:
        connection.rollback()
        connection.close()


def test_inventory_keys_same_model_location_and_critical_model_conflict(clean_environment):
    _, connect, rows, _, truth, _ = clean_environment
    repository = InventoryRepository(connect)
    schema = repository.inspect_schema({c["column"]: c["type"] for c in json.loads((ROOT / "config/schema.json").read_text())["inventory_items"]}, MatchingSettings())
    assert schema.compatible and schema.unique_keys == [["inventory_number"]]
    outputs = {case["document_id"]: reconcile_document(processing_input(case), repository=repository, settings=MatchingSettings())
               for case in truth["scenarios"]}
    first, other = outputs["D01"], outputs["D09"]
    assert first.match_status.value == other.match_status.value == "EXACT_MATCH"
    assert first.matched_record.values["name"] == other.matched_record.values["name"]
    assert first.matched_record.record_id != other.matched_record.record_id
    assert first.search_metadata.inventory_lookup.unique_constraint_verified
    assert not first.search_metadata.fuzzy_search.attempted
    delta = outputs["D02"]
    assert delta.match_status.value == "EXACT_MATCH"
    assert any(a.action_type.value == "UPDATE_CANDIDATE" and a.affected_fields == ["location"] for a in delta.suggested_actions)
    assert outputs["D11"].match_status.value == "AMBIGUOUS_MATCH"
    assert outputs["D12"].match_status.value == "CONFLICTING_DATA"
    assert outputs["D15"].prepared_document.possible_multiple_entities
    assert all(not a.executable for result in outputs.values() for a in result.suggested_actions)


def test_ground_truth_evaluation_on_real_postgres_records_disagreements(clean_environment, tmp_path):
    _, connect, rows, _, truth, report = clean_environment
    actual = evaluate(rows, truth, repository=InventoryRepository(connect), mode="isolated_postgres")
    offline = evaluate(rows, truth)
    keys = ("actual_category", "actual_inventory_number", "actual_differences", "actual_actions", "review_required")
    assert [[c[k] for k in keys] for c in actual["cases"]] == [[c[k] for k in keys] for c in offline["cases"]]
    report["evaluation"] = actual
    write_json(Path(os.getenv("CLEAN_INVENTORY_REPORT_DIR", str(tmp_path))) / "matching_postgres.json", actual)


def test_sql_hybrid_rag_and_streamlit_smoke_with_external_ai_stubs(clean_environment, monkeypatch):
    from app.db import executor
    from app.orchestration import orchestrator
    from streamlit.testing.v1 import AppTest
    from app.web import reconciliation_preview as preview
    _, connect, _, _, truth, _ = clean_environment
    monkeypatch.setattr(executor, "get_connection", connect)
    monkeypatch.setattr(orchestrator, "generate_sql", lambda _: "SELECT inventory_number, name FROM inventory_items WHERE inventory_number = 'L-00001'")
    monkeypatch.setattr(orchestrator, "generate_natural_answer", lambda *args: "Tesztválasz")
    monkeypatch.setattr(orchestrator, "route_query", lambda _: "SQL")
    result = orchestrator.handle_question("Hol van az L-00001 eszköz?")
    assert result["ok"] and result["result"]["rows"][0][0] == "L-00001"
    monkeypatch.setattr(orchestrator, "route_query", lambda _: "HYBRID")
    hybrid = Mock(return_value={"answer": "Dokumentációs tesztválasz", "sources": []})
    monkeypatch.setattr(orchestrator, "answer_hybrid_details", hybrid)
    result = orchestrator.handle_question("Hol van az L-00001 és hogyan működik?")
    assert result["ok"] and result["matched_names"] == ["dell latitude 5540"]
    assert hybrid.call_count == 1
    monkeypatch.setattr(orchestrator, "route_query", lambda _: "RAG")
    monkeypatch.setattr(orchestrator, "answer_rag_details", lambda _: {"answer": "RAG teszt", "sources": []})
    assert orchestrator.handle_question("Hogyan működik a laptop?")["ok"]
    processed = processing_input(truth["scenarios"][1])
    reconciled = reconcile_document(processed, repository=InventoryRepository(connect), settings=MatchingSettings())
    monkeypatch.setattr(preview, "_run_reconciliation", lambda _: reconciled)
    app = AppTest.from_string("from app.web.reconciliation_preview import render_reconciliation\nimport streamlit as st\nrender_reconciliation(st.session_state['processed'])")
    app.session_state["processed"] = processed
    app.run().button[0].click().run()
    assert not app.exception
    assert any("Rekordfrissítés" in item.value for item in app.markdown)
    main = AppTest.from_file(str(ROOT / "app/web/simple_server.py")).run()
    assert not main.exception


def test_reader_role_can_query_but_cannot_modify_inventory(clean_environment):
    _, connect, _, _, _, _ = clean_environment
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE ROLE clean_test_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
            cursor.execute("GRANT USAGE ON SCHEMA public TO clean_test_reader")
            cursor.execute("GRANT SELECT ON public.inventory_items TO clean_test_reader")
            cursor.execute("SET ROLE clean_test_reader")
            cursor.execute("SELECT count(*) FROM public.inventory_items")
            assert cursor.fetchone()[0] == 1000
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute("UPDATE public.inventory_items SET quantity = 1")
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture(scope="module")
def real_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from app.document_processing.config import Settings
    return DocumentConverter(allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={InputFormat.PDF: PdfFormatOption(
            pipeline_options=PdfPipelineOptions(artifacts_path=Settings.from_env().artifacts_path))})


@pytest.mark.parametrize("case_number", range(16))
@pytest.mark.parametrize("suffix", ["docx", "pdf"])
def test_generated_document_real_docling_readability(clean_environment, real_converter, request, case_number, suffix):
    if suffix == "pdf" and not request.config.getoption("--run-docling-pdf"):
        pytest.skip("Enable --run-docling-pdf for real layout/OCR processing")
    from app.document_processing.docling_parser import parse_document
    _, _, _, _, truth, report = clean_environment
    case = truth["scenarios"][case_number]
    path = ROOT / "data/synthetic/documents" / f"{case['document_id']}.{suffix}"
    parsed = parse_document(path.read_bytes(), path.name, converter=real_converter)
    text = " ".join(parsed.extraction_text.split())
    for field in case["expected_fields"]:
        assert " ".join(field["raw"].split()) in text
    report.setdefault("real_docling_readable_documents", []).append(path.name)


@pytest.mark.parametrize("case_number", [0, 1])
@pytest.mark.parametrize("suffix", ["docx", "pdf"])
def test_real_documents_through_processing_with_stubbed_llm_then_postgres(clean_environment, real_converter, request,
                                                                        monkeypatch, case_number, suffix):
    if suffix == "pdf" and not request.config.getoption("--run-docling-pdf"):
        pytest.skip("Enable --run-docling-pdf for real layout/OCR processing")
    from app.document_processing import processing_service
    from app.document_processing.docling_parser import parse_document
    from app.services import llm_service
    _, connect, _, _, truth, report = clean_environment
    case = truth["scenarios"][case_number]
    path = ROOT / "data/synthetic/documents" / f"{case['document_id']}.{suffix}"
    fields = case["expected_fields"]
    llm = Mock(side_effect=[json.dumps({"document_type": "inventory", "fields": [
        {"label": f["label"], "value": f["raw"], "evidence": f"{f['label']}: {f['raw']}"} for f in fields]}),
        json.dumps({"assignments": [{"index": index, "target_field": f["field"]} for index, f in enumerate(fields)]})])
    monkeypatch.setattr(llm_service, "ask_llm", llm)
    monkeypatch.setattr(processing_service, "parse_document", lambda data, name, **kwargs:
                        parse_document(data, name, converter=real_converter, **kwargs))
    processed = processing_service.process_document(path.read_bytes(), path.name)
    result = reconcile_document(processed, repository=InventoryRepository(connect), settings=MatchingSettings())
    assert llm.call_count == 2
    assert assess(case, result)["passed"]
    report.setdefault("docling_processing_postgres_with_stub_llm", []).append(path.name)
