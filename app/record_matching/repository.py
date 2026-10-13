"""Read-only, bounded PostgreSQL retrieval, with verified identity and search scope.

No Text-to-SQL, business writes, extension installation or implicit schema changes.
All stages share one repeatable-read snapshot. Filtered fuzzy searches are partial.
"""
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import math
import re
from time import perf_counter
from typing import Callable
from uuid import UUID

import psycopg2
from psycopg2 import sql

from app.db.connection import get_connection
from app.errors import AppError, DatabaseUnavailableError
from app.services.schema_service import load_schema
from .candidate_service import escape_like, fuzzy_tokens, select_candidates
from .config import IDENTIFIER_FIELDS, MatchingSettings
from .models import CandidateSearchResult, DatabaseRecord, Scalar, SchemaInfo, SearchMetadata


class RepositoryError(AppError):
    def __init__(self, message: str, *, code: str = "MATCHING_DATABASE_ERROR"):
        super().__init__(message, code=code, title="Rekordkeresési hiba")


_COLUMNS_QUERY = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s
ORDER BY ordinal_position
"""
_INDEX_QUERY = """
SELECT ix.indisprimary, ix.indisvalid, ix.indisready, ix.indimmediate,
       ix.indpred IS NULL, ix.indexprs IS NULL,
       ARRAY(SELECT a.attname
             FROM unnest(ix.indkey) WITH ORDINALITY AS k(attnum, position)
             JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
             WHERE k.position <= ix.indnkeyatts ORDER BY k.position)
FROM pg_index ix
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace ns ON ns.oid = t.relnamespace
WHERE ns.nspname = %s AND t.relname = %s AND ix.indisunique
ORDER BY ix.indisprimary DESC, ix.indexrelid
"""
_RELATION_QUERY = """
SELECT t.relkind, t.relrowsecurity,
       EXISTS(SELECT 1 FROM pg_inherits h WHERE h.inhparent = t.oid)
FROM pg_class t JOIN pg_namespace ns ON ns.oid = t.relnamespace
WHERE ns.nspname = %s AND t.relname = %s
"""
_TYPE_ALIASES = {"int": "integer", "int4": "integer", "int8": "bigint", "int2": "smallint",
                 "decimal": "numeric", "varchar": "character varying", "bool": "boolean"}
_SUPPORTED_TYPES = frozenset(("text", "character varying", "character", "integer", "bigint", "smallint",
                             "numeric", "real", "double precision", "date", "boolean", "uuid"))


def _dtype(value: str) -> str:
    return _TYPE_ALIASES.get(value.lower(), value.lower())


def _scalar(value) -> Scalar:
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise RepositoryError("Az adatbázis nem véges numerikus értéket tartalmaz.")
        return format(value, "f")
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise RepositoryError("Nem támogatott adatbázismező-típus az egyeztetésben.")


def record_from_row(row: dict, schema: SchemaInfo) -> DatabaseRecord:
    values = {key: _scalar(value) for key, value in row.items()}
    keys = ([schema.primary_key] if schema.primary_key else []) + schema.unique_keys
    if schema.verified:
        for key in keys:
            if key and all(name in values and values[name] is not None for name in key):
                identity = {name: values[name] for name in key}
                return DatabaseRecord(values=values, identity_fields=key,
                                      record_id=json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                                           separators=(",", ":")))
    return DatabaseRecord(values=values)


class InventoryRepository:
    """Inject a fresh-connection factory for tests; callers never supply SQL."""

    def __init__(self, connection_factory: Callable | None = None):
        self._connection_factory = connection_factory

    @contextmanager
    def _transaction(self, settings: MatchingSettings):
        connection = None
        cursor = None
        try:
            connection = (self._connection_factory() if self._connection_factory else
                          get_connection(connect_timeout=settings.connect_timeout_seconds))
            connection.set_session(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
            cursor = connection.cursor()
            cursor.execute("SELECT set_config('statement_timeout', %s, true)",
                           (str(settings.query_timeout_ms),))
            cursor.execute("SELECT set_config('lock_timeout', %s, true)",
                           (str(settings.query_timeout_ms),))
            yield cursor
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                finally:
                    if connection is not None:
                        connection.close()
            elif connection is not None:
                connection.close()

    def _validate_allowlist(self, expected_columns: dict[str, str], settings: MatchingSettings):
        if settings.target_table not in load_schema():
            raise RepositoryError("A céltábla nem szerepel az engedélyezett sémafájlban.",
                                  code="MATCHING_SCHEMA_ERROR")
        if not expected_columns or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                                       or _dtype(dtype) not in _SUPPORTED_TYPES
                                       for name, dtype in expected_columns.items()):
            raise RepositoryError("Hiányos vagy nem támogatott egyeztetési séma.",
                                  code="MATCHING_SCHEMA_ERROR")

    def _inspect(self, cursor, expected: dict[str, str], settings: MatchingSettings) -> SchemaInfo:
        parameters = (settings.target_schema, settings.target_table)
        cursor.execute(_COLUMNS_QUERY, parameters)
        actual = dict(cursor.fetchall())
        differences = []
        compatible = True
        if not actual:
            differences.append("A céltábla nem található, vagy nincs hozzá olvasási jogosultság.")
            compatible = False
        for name, dtype in expected.items():
            if name not in actual:
                differences.append(f"Hiányzó oszlop: {name}.")
                compatible = False
            elif _dtype(actual[name]) != _dtype(dtype):
                differences.append(f"Eltérő adattípus: {name}: {dtype} / {actual[name]}.")
                compatible = False
        for name in actual.keys() - expected.keys():
            differences.append(f"A sémafájlban nem szereplő adatbázisoszlop: {name}.")
        cursor.execute(_RELATION_QUERY, parameters)
        relation = cursor.fetchone()
        if relation:
            kind, row_security, has_children = relation
            if kind not in ("r", "p") or (kind == "r" and has_children):
                compatible = False
                differences.append("Nézet vagy öröklődő tábla nem támogatott a teljes rekordazonosításhoz.")
            if row_security:
                compatible = False
                differences.append("Row-level security mellett a globális keresési teljesség nem igazolható.")
        cursor.execute(_INDEX_QUERY, parameters)
        primary_key, unique_keys = [], []
        for primary, valid, ready, immediate, nonpartial, nonexpression, key in cursor.fetchall():
            if all((valid, ready, immediate, nonpartial, nonexpression)) and key:
                if all(name in actual and _dtype(actual[name]) in _SUPPORTED_TYPES for name in key):
                    if primary:
                        primary_key = list(key)
                    if list(key) not in unique_keys:
                        unique_keys.append(list(key))
        unique_keys.sort(key=lambda key: (key != primary_key, len(key), key))
        return SchemaInfo(table_schema=settings.target_schema, table_name=settings.target_table,
                          columns=actual, primary_key=primary_key, unique_keys=unique_keys,
                          verified=True, compatible=compatible, differences=differences)

    def inspect_schema(self, expected_columns: dict[str, str], settings: MatchingSettings) -> SchemaInfo:
        self._validate_allowlist(expected_columns, settings)
        try:
            with self._transaction(settings) as cursor:
                return self._inspect(cursor, expected_columns, settings)
        except (DatabaseUnavailableError, psycopg2.Error) as exc:
            raise RepositoryError("Az adatbázisséma ellenőrzése nem sikerült.") from exc

    def _rows(self, cursor, columns: list[str], condition, parameters: list,
              limit: int, schema: SchemaInfo) -> list[DatabaseRecord]:
        identifiers = sql.SQL(", ").join(map(sql.Identifier, columns))
        query = sql.SQL("SELECT {columns} FROM {table} WHERE {condition} ORDER BY {order} LIMIT %s").format(
            columns=identifiers, table=sql.Identifier(schema.table_schema, schema.table_name),
            condition=condition, order=identifiers)
        cursor.execute(query, (*parameters, limit))
        return [record_from_row(dict(zip(columns, row)), schema) for row in cursor.fetchall()]

    def search(self, values: dict[str, Scalar], expected_columns: dict[str, str],
               settings: MatchingSettings) -> CandidateSearchResult:
        start = perf_counter()
        metadata = SearchMetadata(candidate_limit=settings.max_candidates)
        records = []
        try:
            self._validate_allowlist(expected_columns, settings)
            _validate_search_values(values, expected_columns, settings)
            with self._transaction(settings) as cursor:
                schema = self._inspect(cursor, expected_columns, settings)
                metadata.schema_info = schema
                metadata.warnings.extend(schema.differences)
                if not schema.compatible:
                    metadata.scope = "schema_incompatible"
                else:
                    records = self._search(cursor, values, expected_columns, settings, metadata)
        except psycopg2.errors.QueryCanceled:
            metadata.complete = False
            metadata.timed_out = True
            metadata.scope = "timeout"
            metadata.warnings.append("A rekordkeresés túllépte az időkorlátot; nem állapítható meg a rekord hiánya.")
        except (DatabaseUnavailableError, psycopg2.Error) as exc:
            raise RepositoryError("Az adatbázisrekordok lekérése nem sikerült. Az egyeztetés nem teljes.") from exc
        metadata.returned_candidates = len(records)
        metadata.duration_ms = (perf_counter() - start) * 1000
        return CandidateSearchResult(records=records, metadata=metadata)

    def _search(self, cursor, values, expected, settings, metadata):
        schema = metadata.schema_info
        columns = list(expected)
        for key in schema.unique_keys:
            columns.extend(name for name in key if name not in columns)
        if not schema.unique_keys:
            metadata.warnings.append("Nincs igazolt PRIMARY KEY vagy teljes egyedi index; tartós rekordazonosság nem állapítható meg.")
        exact_conditions, exact_parameters = _exact_conditions(values, expected)
        exact_records = []
        if exact_conditions:
            metadata.strategies.append("exact_identifier")
            exact_records = self._rows(cursor, columns, sql.SQL(" OR ").join(exact_conditions),
                                       exact_parameters, settings.max_candidates + 1, schema)
            metadata.scanned_rows += len(exact_records)
            if len(exact_records) > settings.max_candidates:
                metadata.truncated = True
                metadata.scope = "identifier_limit"
                metadata.warnings.append("Az azonosítókeresés elérte a kandidánskorlátot.")
                return exact_records[:settings.max_candidates]
            if settings.strategy == "exact_only" or _verified_identity_lookup(exact_records, values, schema):
                metadata.complete = True
                metadata.scope = "exact_identifiers" if settings.strategy == "exact_only" else "verified_identifier"
                return exact_records
        elif settings.strategy == "exact_only":
            metadata.scope = "no_identifier"
            return []

        # The sentinel prevents unbounded materialization of a large table.
        metadata.strategies.append("bounded_table_scan")
        scanned = self._rows(cursor, columns, sql.SQL("TRUE"), [], settings.max_scan_rows + 1, schema)
        metadata.scanned_rows += len(scanned)
        if len(scanned) <= settings.max_scan_rows:
            records, truncated = select_candidates(scanned, values, settings)
            metadata.complete = not truncated
            metadata.truncated = truncated
            metadata.scope = "full_table"
            if truncated:
                metadata.warnings.append("A teljes táblán végzett keresés eredménye meghaladja a kandidánskorlátot.")
            return records

        conditions, parameters, strategies = _filtered_conditions(values, expected)
        metadata.strategies.extend(strategies)
        metadata.scope = "filtered_subset"
        metadata.complete = False
        metadata.warnings.append("A tábla meghaladja a teljes vizsgálat korlátját; a névalapú előszűrés nem igazolja a rekord globális hiányát.")
        if not conditions:
            return exact_records
        filtered = self._rows(cursor, columns, sql.SQL(" OR ").join(conditions), parameters,
                              settings.max_candidates + 1, schema)
        metadata.scanned_rows += len(filtered)
        metadata.truncated = len(filtered) > settings.max_candidates
        if metadata.truncated:
            metadata.warnings.append("A szűrt keresés elérte a kandidánskorlátot.")
        records, cut = select_candidates(filtered, values, settings)
        metadata.truncated = metadata.truncated or cut
        return records


def _validate_search_values(values, expected, settings):
    for name, value in values.items():
        if name not in expected:
            raise RepositoryError("A keresési mező nincs az engedélyezett sémában.", code="MATCHING_SCHEMA_ERROR")
        if value is None:
            continue
        if isinstance(value, str) and (len(value) > settings.max_field_length or "\x00" in value):
            raise RepositoryError("A keresési mező túl hosszú vagy tiltott karaktert tartalmaz.", code="MATCHING_INPUT_ERROR")
        if type(value) not in (str, int, float, bool) or (type(value) is float and not math.isfinite(value)):
            raise RepositoryError("Érvénytelen keresési mezőérték.", code="MATCHING_INPUT_ERROR")


def _exact_conditions(values, expected):
    conditions, parameters = [], []
    for name in IDENTIFIER_FIELDS:
        if name in expected and values.get(name) not in (None, ""):
            conditions.append(sql.SQL("{} = %s").format(sql.Identifier(name)))
            parameters.append(values[name])
    return conditions, parameters


def _verified_identity_lookup(records, values, schema):
    if len(records) != 1 or records[0].record_id is None:
        return False
    record = records[0]
    if any(values.get(name) is not None and values[name] != record.values.get(name) for name in IDENTIFIER_FIELDS):
        return False
    for key in schema.unique_keys:
        if set(key).issubset({*IDENTIFIER_FIELDS, "sub_code"}) and any(name in IDENTIFIER_FIELDS for name in key):
            if all(values.get(name) is not None and values[name] == record.values.get(name) for name in key):
                return True
    return False


def _filtered_conditions(values, expected):
    conditions, parameters = _exact_conditions(values, expected)
    strategies = []
    for names in (("item_code", "sub_code"), ("name", "location"), ("name", "activation_date")):
        if all(name in expected and values.get(name) not in (None, "") for name in names):
            terms = []
            for name in names:
                if name in ("name", "location"):
                    terms.append(sql.SQL("lower(regexp_replace(btrim({}), '\\s+', ' ', 'g')) = %s").format(sql.Identifier(name)))
                    parameters.append(" ".join(str(values[name]).lower().split()))
                else:
                    terms.append(sql.SQL("{} = %s").format(sql.Identifier(name)))
                    parameters.append(values[name])
            conditions.append(sql.SQL("({})").format(sql.SQL(" AND ").join(terms)))
            strategies.append("composite_" + "_".join(names))
    if "name" in expected and isinstance(values.get("name"), str):
        for token in fuzzy_tokens(values["name"]):
            conditions.append(sql.SQL("{} ILIKE %s").format(sql.Identifier("name")))
            parameters.append("%" + escape_like(token) + "%")
        strategies.append("name_token_prefilter")
    return conditions, parameters, strategies
