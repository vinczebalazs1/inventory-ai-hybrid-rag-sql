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
    assert {row.record_id for row in result.records} == {'{"item_code":"A","sub_code":2}'}
    assert result.metadata.secondary_lookup.complete and not result.metadata.fuzzy_search.attempted
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


@pytest.mark.parametrize("business_key", ["item_code", "inventory_number"])
def test_docx_to_processing_to_postgres_to_streamlit(inventory, monkeypatch, business_key):
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
    execute(sql.SQL("CREATE UNIQUE INDEX document_key ON inventory_items({})").format(sql.Identifier(business_key)))
    execute("INSERT INTO inventory_items(item_code,inventory_number,name,location) VALUES ('DOCX-1','L-DOCX-1','Dell Latitude 5540','Pécs')")
    source_fields = [("Item code", "DOCX-1", "item_code"), ("Device", "Dell Latitude 5540", "name"),
                     ("Location", "Győr", "location")]
    if business_key == "inventory_number":
        source_fields.append(("Leltári szám", "L-DOCX-1", "inventory_number"))
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
    assert output.matched_record.identity_fields == [business_key]
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


def test_inventory_unique_ignores_shared_item_and_large_fuzzy_population(inventory):
    repo, columns, settings, execute = inventory
    execute("CREATE UNIQUE INDEX inv_unique ON inventory_items(inventory_number)")
    execute("INSERT INTO inventory_items(inventory_number,item_code,sub_code,name,location) "
            "SELECT 'L-' || n, 'PRINTER', 0, 'Printer', 'LIB' FROM generate_series(1,4000) n")
    result = repo.search({"inventory_number": "L-942", "item_code": "PRINTER", "sub_code": 0, "name": "Printer"},
                         columns, MatchingSettings(target_schema=settings.target_schema, max_candidates=1, max_scan_rows=1))
    assert len(result.records) == 1 and result.records[0].record_id == '{"inventory_number":"L-942"}'
    assert result.metadata.complete and not result.metadata.truncated
    assert result.metadata.scanned_rows == 1
    assert result.metadata.inventory_lookup.complete and result.metadata.inventory_lookup.unique_constraint_verified
    assert not result.metadata.fuzzy_search.attempted and not result.metadata.absence_check_complete


def test_T20_inventory_injection_and_identifier_characters_remain_literal(inventory):
    repo, columns, settings, execute = inventory
    execute("CREATE UNIQUE INDEX inv_unique ON inventory_items(inventory_number)")
    attack = "L'; DROP TABLE inventory_items; --"
    for value in (attack, "L-001", "L-1", "l-001", " L-001 "):
        execute("INSERT INTO inventory_items(inventory_number) VALUES (%s)", (value,))
        result = repo.search({"inventory_number": value}, columns, settings)
        assert len(result.records) == 1 and result.records[0].values["inventory_number"] == value
    assert execute("SELECT count(*) FROM inventory_items") == [(5,)]


def migration_sql(schema, *, rollback=False):
    """The production SQL is fixed to public; use only a generated test schema here."""
    assert schema.startswith("test_") and schema.replace("_", "").isalnum()
    name = "001_inventory_number_unique" + ("_rollback" if rollback else "") + ".sql"
    return (Path(__file__).resolve().parents[1] / "migrations" / name).read_text(encoding="utf-8").replace("public.", schema + ".")


def test_T18_migration_duplicates_fail_without_invalid_index_or_data_changes(inventory):
    _, _, settings, execute = inventory
    execute("INSERT INTO inventory_items(inventory_number,item_code) VALUES ('DUP','A'),('DUP','B')")
    before = execute("SELECT * FROM inventory_items ORDER BY item_code")
    with pytest.raises(psycopg2.errors.RaiseException, match="Duplicate inventory"):
        execute(migration_sql(settings.target_schema))
    assert execute("SELECT * FROM inventory_items ORDER BY item_code") == before
    assert execute("SELECT count(*) FROM pg_indexes WHERE schemaname=%s", (settings.target_schema,)) == [(0,)]


def test_T19_existing_unique_is_reused_and_not_removed_by_rollback(inventory):
    repo, columns, settings, execute = inventory
    execute("CREATE UNIQUE INDEX existing_inventory_key ON inventory_items(inventory_number) INCLUDE(name)")
    execute(migration_sql(settings.target_schema))
    execute(migration_sql(settings.target_schema, rollback=True))
    assert repo.inspect_schema(columns, settings).unique_keys == [["inventory_number"]]
    assert execute("SELECT indexname FROM pg_indexes WHERE schemaname=%s", (settings.target_schema,)) == [("existing_inventory_key",)]


def test_migration_is_idempotent_nullable_atomic_and_has_guarded_rollback(inventory):
    repo, columns, settings, execute = inventory
    execute("INSERT INTO inventory_items(inventory_number) VALUES ('L-001'), (NULL), (NULL)")
    before = execute("SELECT inventory_number FROM inventory_items ORDER BY inventory_number")
    execute(migration_sql(settings.target_schema))
    execute(migration_sql(settings.target_schema))
    assert repo.inspect_schema(columns, settings).unique_keys == [["inventory_number"]]
    with pytest.raises(psycopg2.errors.UniqueViolation):
        execute("INSERT INTO inventory_items(inventory_number) VALUES ('L-001')")
    assert execute("SELECT inventory_number FROM inventory_items ORDER BY inventory_number") == before
    execute(migration_sql(settings.target_schema, rollback=True))
    assert repo.inspect_schema(columns, settings).unique_keys == []
    assert execute("SELECT inventory_number FROM inventory_items ORDER BY inventory_number") == before


def test_migration_object_name_collision_and_unowned_rollback_are_safe(inventory):
    _, _, settings, execute = inventory
    execute("CREATE INDEX inventory_items_inventory_number_uidx ON inventory_items(name)")
    with pytest.raises(psycopg2.errors.RaiseException, match="name occupied"):
        execute(migration_sql(settings.target_schema))
    with pytest.raises(psycopg2.errors.RaiseException, match="refusing rollback"):
        execute(migration_sql(settings.target_schema, rollback=True))
    assert execute("SELECT count(*) FROM pg_indexes WHERE schemaname=%s", (settings.target_schema,)) == [(1,)]


def test_blank_inventory_blocks_migration_without_forcing_not_null(inventory):
    _, _, settings, execute = inventory
    execute("INSERT INTO inventory_items(inventory_number) VALUES (E' \\t\\n')")
    with pytest.raises(psycopg2.errors.RaiseException, match="Blank inventory"):
        execute(migration_sql(settings.target_schema))
    assert execute("SELECT count(*) FROM pg_indexes WHERE schemaname=%s", (settings.target_schema,)) == [(0,)]


def test_inventory_audit_distinguishes_raw_duplicates_and_normalization_collisions(inventory, monkeypatch):
    from app.record_matching import inventory_audit
    repo, columns, settings, execute = inventory
    monkeypatch.setattr(inventory_audit, "load_schema", lambda: {"inventory_items": [
        {"column": key, "type": value} for key, value in columns.items()]})
    execute("INSERT INTO inventory_items(inventory_number,item_code) VALUES "
            "('DUP','A'),('DUP','B'),('L-001','C'),(' l-001 ','D'),(NULL,'E'),('', 'F'),(E' \\t','G')")
    before = execute("SELECT * FROM inventory_items ORDER BY item_code")
    audit = inventory_audit.audit_inventory_numbers(repo, settings, sample_limit=1)
    assert audit["duplicate_groups"] == 1 and audit["duplicate_rows"] == 2
    assert audit["counts"]["null"] == audit["counts"]["empty"] == audit["counts"]["whitespace_only"] == 1
    assert audit["normalization_collision_groups"] == 2  # blank variants and L-001
    assert audit["normalization_collision_samples_truncated"]
    assert audit["duplicate_samples"][0]["records_truncated"]
    assert not audit["migration_ready"]
    assert execute("SELECT * FROM inventory_items ORDER BY item_code") == before


def test_isolated_inventory_search_benchmark(inventory, tmp_path):
    """Comparable fresh SQL measurements: previous OR lookup vs primary lookup."""
    from datetime import datetime, timezone
    from hashlib import sha256
    import json
    from time import perf_counter
    from app.evaluation.metrics import _timing_summary
    from app.evaluation.runner import implementation_hashes
    from app.record_matching.models import SearchMetadata

    repo, columns, settings, execute = inventory
    execute("CREATE UNIQUE INDEX inv_unique ON inventory_items(inventory_number)")
    execute("INSERT INTO inventory_items(inventory_number,item_code,sub_code,name,location) "
            "SELECT 'L-' || n, 'PRINTER', 0, 'Printer', 'LIB' FROM generate_series(1,4000) n")
    execute("ANALYZE inventory_items")
    settings = MatchingSettings(target_schema=settings.target_schema, max_candidates=1, max_scan_rows=1000)
    values = {"inventory_number": "L-1234", "item_code": "PRINTER", "sub_code": 0, "name": "Printer"}
    timings = {mode: [] for mode in ("previous_or_lookup", "primary_inventory_lookup", "fuzzy_fallback")}
    stats = {}
    with repo._transaction(settings) as cursor:
        schema = repo._inspect(cursor, columns, settings)
        for iteration in range(55):  # Five warmups, then 50 interleaved measurements.
            for mode in timings:
                start = perf_counter()
                if mode == "previous_or_lookup":
                    rows = repo._rows(cursor, list(columns),
                        sql.SQL("inventory_number = %s OR item_code = %s"),
                        [values["inventory_number"], values["item_code"]], settings.max_candidates + 1, schema)
                    metadata = SearchMetadata(complete=len(rows) <= settings.max_candidates,
                                              truncated=len(rows) > settings.max_candidates, scanned_rows=len(rows))
                else:
                    metadata = SearchMetadata(schema_info=schema, candidate_limit=settings.max_candidates)
                    rows = repo._search(cursor, values if mode == "primary_inventory_lookup" else {"name": "Printer"},
                                        columns, settings, metadata)
                elapsed = (perf_counter() - start) * 1000
                if iteration >= 5:
                    timings[mode].append(elapsed)
                stats[mode] = {"complete_for_scope": metadata.complete, "truncated": metadata.truncated,
                               "materialized_rows": metadata.scanned_rows, "returned_rows": len(rows)}
    assert stats["primary_inventory_lookup"]["complete_for_scope"]
    assert stats["primary_inventory_lookup"]["materialized_rows"] == 1
    assert stats["previous_or_lookup"]["truncated"] and stats["fuzzy_fallback"]["truncated"]
    root = Path(__file__).resolve().parents[1]
    source_hash, _ = implementation_hashes(root)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "rows": 4000, "repeats": 50,
              "warmup_iterations": 5, "implementation_sha256": source_hash,
              "benchmark_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "measurement_scope": "Isolated PostgreSQL; existing read-only connection/snapshot; schema audit and connection setup excluded for every mode.",
              "baseline": "Previous OR inventory_number/item_code SQL with the original sentinel cutoff. Query stage only, not a replay of the old full application.",
              "stats": stats, "timings": {mode: _timing_summary(samples) for mode, samples in timings.items()}}
    report["primary_minus_previous_mean_ms"] = (report["timings"]["primary_inventory_lookup"]["mean_ms"]
                                                - report["timings"]["previous_or_lookup"]["mean_ms"])
    destination = Path(os.getenv("MATCHING_BENCHMARK_OUTPUT", str(tmp_path / "inventory_search_benchmark.json")))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
