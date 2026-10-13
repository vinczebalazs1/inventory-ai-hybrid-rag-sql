"""Repository contract/security tests with deterministic DB-API fakes."""
from datetime import date
from decimal import Decimal

import psycopg2
import pytest

from app.record_matching.config import MatchingSettings
from app.record_matching.models import SchemaInfo
from app.record_matching.repository import InventoryRepository, RepositoryError, record_from_row

EXPECTED = {"inventory_number": "text", "item_code": "text", "name": "text"}


class Cursor:
    def __init__(self, batches=(), columns=None, indexes=None, fail=None):
        self.batches = list(batches)
        self.columns = list((columns or EXPECTED).items())
        self.indexes = indexes or []
        self.fail = fail
        self.calls = []
        self.current = []
        self.closed = False

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        if isinstance(query, str):
            if "information_schema.columns" in query:
                self.current = self.columns
            elif "FROM pg_index" in query:
                self.current = self.indexes
            elif "t.relkind" in query:
                self.current = [("r", False, False)]
            else:
                self.current = []
        else:
            if self.fail:
                raise self.fail
            self.current = self.batches.pop(0)

    def fetchall(self):
        return self.current

    def fetchone(self):
        return self.current[0] if self.current else None

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, cursor):
        self.cursor_object = cursor
        self.closed = False
        self.options = {}

    def set_session(self, **kwargs):
        self.options = kwargs

    def cursor(self):
        return self.cursor_object

    def close(self):
        self.closed = True


def setup_repository(**kwargs):
    cursor = Cursor(**kwargs)
    connection = Connection(cursor)
    return InventoryRepository(lambda: connection), connection, cursor


def test_transaction_is_readonly_repeatable_and_resources_close():
    repository, connection, cursor = setup_repository(batches=[[]])
    result = repository.search({"name": "Dell"}, EXPECTED, MatchingSettings())
    assert result.metadata.complete
    assert connection.options == {"readonly": True, "autocommit": False, "isolation_level": "REPEATABLE READ"}
    assert cursor.closed and connection.closed
    assert cursor.calls[0][1] == ("3000",)
    assert all(not (isinstance(q, str) and q.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE")))
               for q, _ in cursor.calls)


def test_sql_injection_is_only_a_bound_value():
    attack = "'; DROP TABLE inventory_items; --"
    repository, _, cursor = setup_repository(batches=[[]])
    result = repository.search({"inventory_number": attack}, EXPECTED,
                               MatchingSettings(strategy="exact_only"))
    query, parameters = cursor.calls[-1]
    assert attack not in repr(query)
    assert parameters == (attack, 101)
    assert result.metadata.complete


def test_unapproved_columns_are_rejected_before_connect():
    called = []
    repository = InventoryRepository(lambda: called.append(True))
    with pytest.raises(RepositoryError):
        repository.search({"name); DROP TABLE x": "x"}, EXPECTED, MatchingSettings())
    assert not called


def test_invalid_schema_identifiers_and_long_values_rejected():
    repository, _, _ = setup_repository()
    with pytest.raises(RepositoryError):
        repository.search({}, {"name); DROP TABLE x": "text"}, MatchingSettings())
    with pytest.raises(RepositoryError):
        repository.search({"name": "x" * 1001}, EXPECTED, MatchingSettings())
    with pytest.raises(RepositoryError):
        repository.search({"name": "x\x00y"}, EXPECTED, MatchingSettings())


def test_live_schema_mismatch_is_not_a_complete_empty_search():
    repository, connection, cursor = setup_repository(columns={"name": "integer"})
    result = repository.search({"name": "Dell"}, EXPECTED, MatchingSettings())
    assert not result.metadata.complete
    assert result.metadata.scope == "schema_incompatible"
    assert not result.metadata.schema_info.compatible
    assert connection.closed and cursor.closed


def test_partial_and_expression_unique_indexes_are_not_stable_keys():
    indexes = [(False, True, True, True, False, True, ["inventory_number"]),
               (False, True, True, True, True, False, ["item_code"]),
               (False, True, True, False, True, True, ["name"])]
    repository, _, _ = setup_repository(indexes=indexes)
    info = repository.inspect_schema(EXPECTED, MatchingSettings())
    assert info.unique_keys == []


def test_unique_nonnull_identifier_can_finish_without_scan():
    repository, _, cursor = setup_repository(
        indexes=[(True, True, True, True, True, True, ["inventory_number"])],
        batches=[[("INV-1", "IT-1", "Dell")]])
    result = repository.search({"inventory_number": "INV-1"}, EXPECTED, MatchingSettings())
    assert result.metadata.scope == "verified_identifier"
    assert result.metadata.complete
    assert result.records[0].record_id == '{"inventory_number":"INV-1"}'
    assert result.records[0].identity_fields == ["inventory_number"]


def test_duplicate_identifier_rows_remain_and_have_no_invented_identity():
    rows = [("INV-1", "IT-1", "Dell"), ("INV-1", "IT-1", "Dell")]
    repository, _, _ = setup_repository(batches=[rows, rows])
    result = repository.search({"inventory_number": "INV-1"}, EXPECTED, MatchingSettings())
    assert len(result.records) == 2
    assert all(record.record_id is None for record in result.records)
    assert result.metadata.complete


def test_sentinel_candidate_limit_is_incomplete():
    rows = [("INV-1", "IT-1", "Dell"), ("INV-1", "IT-2", "Dell")]
    repository, _, _ = setup_repository(batches=[rows])
    result = repository.search({"inventory_number": "INV-1"}, EXPECTED, MatchingSettings(max_candidates=1))
    assert len(result.records) == 1
    assert result.metadata.truncated and not result.metadata.complete


def test_large_table_filtered_empty_is_still_incomplete():
    rows = [("INV-1", "IT-1", "Dell"), ("INV-2", "IT-2", "Dell")]
    repository, _, cursor = setup_repository(batches=[rows, []])
    result = repository.search({"name": "Printer"}, EXPECTED,
                               MatchingSettings(max_candidates=1, max_scan_rows=1))
    assert result.records == []
    assert not result.metadata.complete
    assert result.metadata.scope == "filtered_subset"
    assert cursor.calls[-1][1] == ("%printer%", 2)


def test_timeout_is_incomplete_and_always_releases_resources():
    repository, connection, cursor = setup_repository(fail=psycopg2.errors.QueryCanceled())
    result = repository.search({"name": "Printer"}, EXPECTED, MatchingSettings())
    assert result.metadata.timed_out and not result.metadata.complete
    assert connection.closed and cursor.closed


def test_connection_failure_has_safe_app_error():
    def fail():
        raise psycopg2.OperationalError("password=SECRET hostname=PRIVATE")
    with pytest.raises(RepositoryError) as captured:
        InventoryRepository(fail).search({"name": "Printer"}, EXPECTED, MatchingSettings())
    assert "SECRET" not in str(captured.value)
    assert captured.value.detail is None


def test_decimal_date_and_nullable_identity_serialize_without_precision_loss():
    schema = SchemaInfo(verified=True, unique_keys=[["inventory_number"]])
    record = record_from_row({"inventory_number": None, "purchase_value": Decimal("9999999999999999.01"),
                              "activation_date": date(2025, 1, 1)}, schema)
    assert record.record_id is None
    assert record.values["purchase_value"] == "9999999999999999.01"
    assert record.values["activation_date"] == "2025-01-01"
    assert "9999999999999999.01" in record.model_dump_json()


def test_nonfinite_database_value_is_rejected():
    with pytest.raises(RepositoryError):
        record_from_row({"purchase_value": Decimal("NaN")}, SchemaInfo())
