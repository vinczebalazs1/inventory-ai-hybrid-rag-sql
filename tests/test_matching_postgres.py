"""Real PostgreSQL in a disposable loopback-only cluster; never uses DB_* values."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

from app.record_matching.config import MatchingSettings
from app.record_matching.repository import InventoryRepository


@pytest.fixture(scope="module")
def isolated_postgres(request, tmp_path_factory):
    if not request.config.getoption("--run-matching-postgres"):
        pytest.skip("Enable --run-matching-postgres for an isolated real PostgreSQL cluster")
    binary_dir = Path(os.getenv("MATCHING_TEST_PG_BIN", "C:/Program Files/PostgreSQL/18/bin"))
    extension = ".exe" if os.name == "nt" else ""
    initdb = binary_dir / ("initdb" + extension)
    pg_ctl = binary_dir / ("pg_ctl" + extension)
    if not initdb.is_file():
        located = shutil.which("initdb")
        if located:
            initdb, pg_ctl = Path(located), Path(located).parent / ("pg_ctl" + extension)
        else:
            pytest.skip("PostgreSQL initdb is unavailable; set MATCHING_TEST_PG_BIN")
    directory = tmp_path_factory.mktemp("inventory_matching_pg").resolve()
    base = tmp_path_factory.getbasetemp().resolve()
    assert directory.is_relative_to(base)
    data = directory / "cluster"
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": 60}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run([str(initdb), "-D", str(data), "--username=matching_test", "--auth=trust", "--no-locale", "--encoding=UTF8"],
                   check=True, **kwargs)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    # A long-lived Windows child may inherit pipe handles. Direct startup output
    # to a file so subprocess.run does not wait for server-lifetime pipe EOF.
    control_kwargs = {key: value for key, value in kwargs.items() if key != "capture_output"}
    with (directory / "control.log").open("w", encoding="utf-8") as control:
        subprocess.run([str(pg_ctl), "-D", str(data), "-l", str(directory / "postgres.log"), "-w", "-t", "30",
                        "-o", f"-h 127.0.0.1 -p {port} -c fsync=off", "start"],
                       stdout=control, stderr=subprocess.STDOUT, check=True, **control_kwargs)
    def connect():
        return psycopg2.connect(host="127.0.0.1", port=port, dbname="postgres", user="matching_test", connect_timeout=5)
    try:
        yield connect
    finally:
        subprocess.run([str(pg_ctl), "-D", str(data), "-w", "-t", "30", "-m", "fast", "stop"], check=True, **kwargs)


@pytest.fixture
def inventory(isolated_postgres):
    schema = "test_" + uuid4().hex
    connection = isolated_postgres()
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("CREATE TABLE {}.inventory_items (item_code text, sub_code integer, inventory_number text, name text, location text)").format(sql.Identifier(schema)))
    connection.close()
    expected = {"item_code": "text", "sub_code": "integer", "inventory_number": "text", "name": "text", "location": "text"}
    settings = MatchingSettings(target_schema=schema)
    repository = InventoryRepository(isolated_postgres)
    def execute(statement, params=()):
        connection = isolated_postgres()
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                cursor.execute(statement, params)
                return cursor.fetchall() if cursor.description else None
        finally:
            connection.close()
    return repository, expected, settings, execute


def test_live_readonly_transaction_rejects_writes_and_preserves_data(inventory):
    repo, columns, settings, execute = inventory
    execute("INSERT INTO inventory_items (item_code,name) VALUES (%s,%s)", ("A", "Dell Latitude 5540"))
    before = execute("SELECT * FROM inventory_items")
    with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
        with repo._transaction(settings) as cursor:
            cursor.execute("SHOW transaction_read_only")
            assert cursor.fetchone()[0] == "on"
            cursor.execute(sql.SQL("UPDATE {}.inventory_items SET name='forbidden'").format(sql.Identifier(settings.target_schema)))
    result = repo.search({"item_code": "A"}, columns, settings)
    assert result.metadata.complete and result.records[0].record_id is None
    assert execute("SELECT * FROM inventory_items") == before


def test_live_composite_key_and_parameterized_injection(inventory):
    repo, columns, settings, execute = inventory
    execute("ALTER TABLE inventory_items ADD PRIMARY KEY (item_code, sub_code)")
    execute("INSERT INTO inventory_items(item_code,sub_code,name) VALUES ('A',1,'Dell'),('A',2,'Dell')")
    result = repo.search({"item_code": "A", "sub_code": 2}, columns, settings)
    assert result.metadata.schema_info.primary_key == ["item_code", "sub_code"]
    assert {row.record_id for row in result.records} == {'{"item_code":"A","sub_code":1}', '{"item_code":"A","sub_code":2}'}
    attack = "A'; DROP TABLE inventory_items; --"
    result = repo.search({"item_code": attack}, columns, settings)
    assert not result.records and result.metadata.complete
    assert execute("SELECT count(*) FROM inventory_items") == [(2,)]


def test_live_unique_identifier_can_finish_without_global_scan(inventory):
    repo, columns, settings, execute = inventory
    execute("CREATE UNIQUE INDEX inv_unique ON inventory_items(inventory_number)")
    execute("INSERT INTO inventory_items(inventory_number,name) VALUES ('INV-1','Dell'),(NULL,'Dell')")
    result = repo.search({"inventory_number": "INV-1"}, columns, settings)
    assert result.metadata.scope == "verified_identifier" and result.metadata.complete
    assert result.records[0].identity_fields == ["inventory_number"]
    result = repo.search({"name": "Dell"}, columns, settings)
    assert any(row.record_id is None for row in result.records)


def test_live_partial_expression_indexes_are_not_identities(inventory):
    repo, columns, settings, execute = inventory
    execute("CREATE UNIQUE INDEX partial_key ON inventory_items(item_code) WHERE sub_code=1")
    execute("CREATE UNIQUE INDEX expression_key ON inventory_items(lower(inventory_number))")
    schema = repo.inspect_schema(columns, settings)
    assert schema.verified and schema.compatible and schema.unique_keys == []


def test_live_limits_and_incomplete_fuzzy_search(inventory):
    repo, columns, settings, execute = inventory
    execute("INSERT INTO inventory_items(item_code,name) VALUES ('A','Dell Latitude 5540'),('B','Dell Latitude 5540'),('C','Dell Latitude 5540')")
    settings = MatchingSettings(target_schema=settings.target_schema, max_candidates=1, max_scan_rows=2)
    result = repo.search({"name": "Dell Latitude 5540"}, columns, settings)
    assert result.metadata.scope == "filtered_subset"
    assert result.metadata.truncated and not result.metadata.complete and len(result.records) == 1


def test_live_timeout_and_schema_mismatch_are_incomplete(inventory):
    repo, columns, settings, execute = inventory
    class SlowRepository(InventoryRepository):
        def _inspect(self, cursor, expected, settings):
            cursor.execute("SELECT pg_sleep(0.1)")
            return super()._inspect(cursor, expected, settings)
    slow = SlowRepository(repo._connection_factory)
    result = slow.search({"item_code": "A"}, columns, MatchingSettings(target_schema=settings.target_schema, query_timeout_ms=1))
    assert result.metadata.timed_out and not result.metadata.complete
    result = repo.search({"item_code": "A"}, {**columns, "quantity": "integer"}, settings)
    assert result.metadata.scope == "schema_incompatible" and not result.metadata.complete
    assert any("quantity" in difference for difference in result.metadata.schema_info.differences)


def test_docx_to_processing_to_postgres_to_streamlit(inventory, monkeypatch):
    """Real parser, extraction/mapping contracts, SQL, matcher and rendered result."""
    from io import BytesIO
    import json
    from unittest.mock import Mock
    from docx import Document
    from streamlit.testing.v1 import AppTest
    from app.document_processing.processing_service import process_document
    from app.record_matching.reconciliation_service import reconcile_document
    from app.record_matching.models import MatchStatus, ActionType
    from app.services import llm_service
    import app.web.reconciliation_preview as preview

    repo, columns, settings, execute = inventory
    execute("ALTER TABLE inventory_items ADD PRIMARY KEY(item_code)")
    execute("INSERT INTO inventory_items(item_code,name,location) VALUES ('DOCX-1','Dell Latitude 5540','Pécs')")
    source_fields = [("Item code", "DOCX-1", "item_code"), ("Device", "Dell Latitude 5540", "name"),
                     ("Location", "Győr", "location")]
    document = Document()
    for label, value, _ in source_fields:
        document.add_paragraph(f"{label}: {value}")
    buffer = BytesIO()
    document.save(buffer)
    llm = Mock(side_effect=[json.dumps({"document_type": "inventory", "fields": [
        {"label": label, "value": value, "evidence": f"{label}: {value}"} for label, value, _ in source_fields]}),
        json.dumps({"assignments": [{"index": index, "target_field": target} for index, (_, _, target) in enumerate(source_fields)]})])
    monkeypatch.setattr(llm_service, "ask_llm", llm)
    processed = process_document(buffer.getvalue(), "inventory.docx")
    output = reconcile_document(processed, repository=repo, settings=settings, columns=columns)
    assert output.match_status == MatchStatus.EXACT_MATCH
    assert ActionType.UPDATE_CANDIDATE in {action.action_type for action in output.suggested_actions}
    assert llm.call_count == 2
    run = Mock(return_value=output)
    monkeypatch.setattr(preview, "_run_reconciliation", run)
    app = AppTest.from_string("from app.web.reconciliation_preview import render_reconciliation\nimport streamlit as st\nrender_reconciliation(st.session_state['processed'])")
    app.session_state["processed"] = processed
    app.run().button[0].click().run()
    app.run()
    assert not app.exception and run.call_count == 1 and llm.call_count == 2
    assert any("Rekordfrissítés" in item.value for item in app.markdown)
    assert execute("SELECT location FROM inventory_items") == [("Pécs",)]
