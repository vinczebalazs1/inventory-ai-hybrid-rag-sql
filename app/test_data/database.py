"""Fail-closed tooling for one named test database; application connections stay unchanged."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import re
from time import perf_counter

from dotenv import dotenv_values
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from .artifacts import ROOT, dataset_hash
from .models import COLUMNS, InventoryRow
from .validation import require_valid, validate_rows

TARGET = "inventory_ai_clean"
TABLE_MARKER = "InventoryAI clean dataset v1: managed synthetic table"
CHECKS = {
    "clean_inventory_format": "inventory_number ~ '^L-[0-9]{5,}$'",
    "clean_quantity_one": "quantity = 1",
    "clean_name_nonblank": "name ~ '[^[:space:]]'",
    "clean_item_nonblank": "item_code ~ '[^[:space:]]'",
    "clean_location_nonblank": "location ~ '[^[:space:]]'",
    "clean_purchase_nonnegative": "purchase_value >= 0",
    "clean_depreciation_nonnegative": "depreciation >= 0",
    "clean_current_nonnegative": "current_value >= 0",
    "clean_currency_code": "currency ~ '^[A-Z]{3}$'",
}


class CleanDatabaseError(ValueError):
    """Messages are controlled by us; never include driver credentials or DSNs."""


@dataclass(frozen=True, repr=False)
class ConnectionConfig:
    name: str
    user: str
    password: str
    host: str
    port: int

    @classmethod
    def from_env(cls, path: Path):
        if not path.is_file():
            raise CleanDatabaseError("Hiányzó konfigurációs fájl; készíts helyi másolatot a .env.clean.example alapján.")
        file_values = dotenv_values(path, interpolate=False)
        values = {}
        for key in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
            inherited, saved = os.getenv(key), file_values.get(key)
            if inherited is not None and saved is not None and inherited != saved:
                raise CleanDatabaseError(f"Eltérő shell- és fájlbeállítás: {key}. A cél nem választható ki észrevétlenül.")
            values[key] = inherited if inherited is not None else saved
            if not values[key]:
                raise CleanDatabaseError(f"Hiányzó konfiguráció: {key}")
        config = cls(values["DB_NAME"], values["DB_USER"], values["DB_PASSWORD"], values["DB_HOST"], int(values["DB_PORT"]))
        config.require_target()
        return config

    def require_target(self):
        if self.name != TARGET:
            raise CleanDatabaseError("DB_NAME kizárólag inventory_ai_clean lehet.")
        if not 1 <= self.port <= 65535:
            raise CleanDatabaseError("Érvénytelen DB_PORT.")

    def connect(self, *, maintenance=False):
        self.require_target()
        return psycopg2.connect(dbname="postgres" if maintenance else self.name, user=self.user,
                               password=self.password, host=self.host, port=self.port, connect_timeout=5)


def require_confirmation(apply: bool, confirm_db: str | None):
    if apply and confirm_db != TARGET:
        raise CleanDatabaseError("Íráshoz --apply --confirm-db inventory_ai_clean szükséges.")
    if confirm_db is not None and confirm_db != TARGET:
        raise CleanDatabaseError("Eltérő megerősített adatbázis; a művelet tiltott.")


def require_database(cursor, expected=TARGET):
    cursor.execute("SELECT current_database()")
    if cursor.fetchone()[0] != expected:
        raise CleanDatabaseError("A tényleges PostgreSQL-adatbázis eltér az engedélyezett céltól.")


@contextmanager
def transaction(config, *, writable=False, connection_factory=None):
    config.require_target()
    connection = (connection_factory or config.connect)()
    try:
        connection.set_session(readonly=not writable, autocommit=False,
                               isolation_level="READ COMMITTED" if writable else "REPEATABLE READ")
        with connection.cursor() as cursor:
            require_database(cursor)
            cursor.execute("SELECT set_config('statement_timeout', '60000', true)")
            cursor.execute("SELECT set_config('lock_timeout', '5000', true)")
            cursor.execute("SELECT set_config('search_path', 'pg_catalog', true)")
            yield cursor
        if writable:
            connection.commit()
        else:
            connection.rollback()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_database(config, *, apply=False, confirm_db=None, connection_factory=None):
    """CREATE DATABASE is the sole autocommit operation, against postgres only."""
    require_confirmation(apply, confirm_db)
    config.require_target()
    connection = (connection_factory or (lambda: config.connect(maintenance=True)))()
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            require_database(cursor, "postgres")
            cursor.execute("SELECT set_config('statement_timeout', '60000', false)")
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TARGET,))
            exists = cursor.fetchone() is not None
            if apply and not exists:
                require_database(cursor, "postgres")
                try:
                    cursor.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(TARGET)))
                except psycopg2.errors.DuplicateDatabase:
                    # Another operator may have created it after our SELECT. No adoption/seed.
                    exists = True
            return {"database": TARGET, "operation": "create_database", "dry_run": not apply,
                    "status": "already_exists" if exists else "created" if apply else "would_create"}
    finally:
        connection.close()


def schema_report(cursor) -> dict:
    """SELECT-only structural verification; constraint names alone are insufficient."""
    import json
    from app.record_matching.repository import InventoryRepository
    from app.record_matching.config import MatchingSettings
    expected = {c["column"]: c["type"] for c in json.loads((ROOT / "config/schema.json").read_text(encoding="utf-8"))["inventory_items"]}
    require_database(cursor)
    cursor.execute("SELECT to_regclass('public.inventory_items')")
    if cursor.fetchone()[0] is None:
        return {"schema_compatible": False, "constraints_verified": False, "errors": ["Hiányzó céltábla."]}
    schema = InventoryRepository()._inspect(cursor, expected, MatchingSettings())
    errors = list(schema.differences)
    if not schema.compatible or list(schema.columns.items()) != list(expected.items()) or list(expected) != list(COLUMNS):
        errors.append("A tábla nem pontosan a konfigurált 11 mezőt tartalmazza.")
    cursor.execute("SELECT attname, attnotnull, attidentity, attgenerated FROM pg_attribute "
                   "WHERE attrelid='public.inventory_items'::regclass AND attnum>0 AND NOT attisdropped")
    attributes = cursor.fetchall()
    if any(not notnull or identity or generated for _, notnull, identity, generated in attributes):
        errors.append("A clean mezők kötelező NOT NULL/egyszerű oszlop feltétele eltér.")
    cursor.execute("SELECT obj_description('public.inventory_items'::regclass, 'pg_class'), "
        "EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='public.inventory_items'::regclass AND NOT tgisinternal), "
        "EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class='public.inventory_items'::regclass), "
        "EXISTS(SELECT 1 FROM pg_inherits WHERE inhrelid='public.inventory_items'::regclass OR inhparent='public.inventory_items'::regclass), "
        "(SELECT relkind FROM pg_class WHERE oid='public.inventory_items'::regclass)")
    marker, triggers, rules, inheritance, kind = cursor.fetchone()
    if marker != TABLE_MARKER or triggers or rules or inheritance or kind != 'r':
        errors.append("Nem igazolt clean tábla, trigger, szabály vagy öröklődés.")
    cursor.execute("SELECT conname, pg_get_expr(conbin, conrelid), convalidated, connoinherit "
                   "FROM pg_constraint WHERE conrelid='public.inventory_items'::regclass AND contype='c'")
    checks = {name: (expression, valid, noinherit) for name, expression, valid, noinherit in cursor.fetchall()}
    def normalized(expression):
        return re.sub(r"[()\s]", "", expression.replace("::text", ""))
    verified = {name: name in checks and checks[name][1] and not checks[name][2]
                and normalized(checks[name][0]) == normalized(expression) for name, expression in CHECKS.items()}
    if not all(verified.values()):
        errors.append("Hiányzó, érvénytelen vagy eltérő CHECK definíció.")
    if schema.unique_keys != [["inventory_number"]]:
        errors.append("Az egyetlen üzleti UNIQUE kulcs inventory_number kell legyen.")
    return {"schema_compatible": schema.compatible and list(schema.columns.items()) == list(expected.items()),
            "constraints_verified": not errors, "checks": verified, "unique_keys": schema.unique_keys,
            "not_null_columns": sorted(name for name, valid, _, _ in attributes if valid), "errors": errors}


def require_schema(cursor):
    report = schema_report(cursor)
    if not report["schema_compatible"] or not report["constraints_verified"]:
        raise CleanDatabaseError("; ".join(report["errors"]))
    return report


def migrate(config, *, apply=False, confirm_db=None, connection_factory=None):
    require_confirmation(apply, confirm_db)
    files = [ROOT / "migrations/clean" / name for name in
             ("001_create_inventory_items.sql", "002_add_inventory_constraints.sql")]
    with transaction(config, writable=apply, connection_factory=connection_factory) as cursor:
        if apply:
            # Transaction-scoped lock serializes concurrent cooperative migrations.
            cursor.execute("SELECT pg_advisory_xact_lock(17012026, 1)")
            for path in files:
                require_database(cursor)
                cursor.execute(path.read_text(encoding="utf-8"))
            report = require_schema(cursor)
        else:
            report = schema_report(cursor)
    return {"database": TARGET, "operation": "migrate", "dry_run": not apply,
            "migrations": [p.name for p in files], "status": "applied" if apply else "inspection_only", **report}


def stored_rows(cursor, limit: int) -> tuple[int, list[InventoryRow]]:
    cursor.execute("SELECT count(*) FROM public.inventory_items")
    count = cursor.fetchone()[0]
    if count > limit:
        raise CleanDatabaseError("A céltábla több rekordot tartalmaz a várt készletnél; nincs automatikus adatjavítás.")
    cursor.execute(sql.SQL("SELECT {} FROM public.inventory_items ORDER BY inventory_number").format(
        sql.SQL(', ').join(map(sql.Identifier, COLUMNS))))
    rows = []
    while batch := cursor.fetchmany(500):
        rows.extend(InventoryRow.model_validate({name: value.isoformat() if isinstance(value, date) else value
                    for name, value in zip(COLUMNS, row)}) for row in batch)
    return count, rows


def load_dataset(config, rows, generation_config, *, apply=False, confirm_db=None,
                 batch_size=250, connection_factory=None):
    require_confirmation(apply, confirm_db)
    require_valid(rows, generation_config)
    if not 1 <= batch_size <= 5000:
        raise CleanDatabaseError("batch_size must be between 1 and 5000")
    started = perf_counter()
    with transaction(config, writable=apply, connection_factory=connection_factory) as cursor:
        if apply:
            # Serialize loaders and exclude concurrent writers/DDL before checking emptiness.
            cursor.execute("LOCK TABLE public.inventory_items IN SHARE ROW EXCLUSIVE MODE")
        require_schema(cursor)
        count, current = stored_rows(cursor, generation_config.count)
        already_loaded = count == len(rows) and dataset_hash(current) == dataset_hash(rows)
        if count and not already_loaded:
            raise CleanDatabaseError("A céltábla nem üres és eltér a készlettől; nincs törlés vagy felülírás.")
        if apply and not already_loaded:
            statement = sql.SQL("INSERT INTO public.inventory_items ({}) VALUES %s").format(
                sql.SQL(', ').join(map(sql.Identifier, COLUMNS))).as_string(cursor)
            for start in range(0, len(rows), batch_size):
                require_database(cursor)
                batch = [tuple(row.model_dump()[name] for name in COLUMNS) for row in rows[start:start + batch_size]]
                execute_values(cursor, statement, batch, page_size=batch_size)
            count, current = stored_rows(cursor, generation_config.count)
            if count != len(rows) or dataset_hash(current) != dataset_hash(rows):
                raise CleanDatabaseError("Import utáni ellenőrzés sikertelen; teljes rollback.")
    return {"database": TARGET, "operation": "load", "dry_run": not apply,
            "status": "already_loaded" if already_loaded else "loaded" if apply else "would_load",
            "record_count": count, "planned_count": len(rows), "canonical_dataset_sha256": dataset_hash(rows),
            "duration_ms": (perf_counter() - started) * 1000}


def verify_dataset(config, expected_rows, generation_config, *, connection_factory=None):
    require_valid(expected_rows, generation_config)
    started = perf_counter()
    with transaction(config, connection_factory=connection_factory) as cursor:
        structure = schema_report(cursor)
        if not structure["schema_compatible"] or not structure["constraints_verified"]:
            return {"database": TARGET, "read_only": True, **structure, "validation_passed": False}
        count, rows = stored_rows(cursor, generation_config.count)
        quality = validate_rows(rows, generation_config)
        hash_verified = dataset_hash(rows) == dataset_hash(expected_rows)
    return {"database": TARGET, "read_only": True, **structure, **quality,
            "dataset_hash_verified": hash_verified, "canonical_dataset_sha256": dataset_hash(rows),
            "validation_passed": quality["validation_passed"] and hash_verified,
            "duration_ms": (perf_counter() - started) * 1000}
