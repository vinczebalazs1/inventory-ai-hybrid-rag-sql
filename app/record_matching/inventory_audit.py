"""Read-only audit of the existing business key; never repairs inventory data."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from psycopg2 import sql

from .config import MatchingSettings
from .repository import InventoryRepository, _scalar
from app.services.schema_service import load_schema


def audit_inventory_numbers(repository: InventoryRepository | None = None,
                            settings: MatchingSettings | None = None, *, sample_limit: int = 50) -> dict:
    if not 1 <= sample_limit <= 1000:
        raise ValueError("sample_limit must be between 1 and 1000")
    repository, settings = repository or InventoryRepository(), settings or MatchingSettings.from_env()
    expected = {c["column"]: c["type"] for c in load_schema()[settings.target_table]}
    repository._validate_allowlist(expected, settings)
    report = {"audited_at_utc": datetime.now(timezone.utc).isoformat(), "read_only": True,
              "audit_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "sample_limit": sample_limit, "blockers": [], "warnings": []}
    with repository._transaction(settings) as cursor:
        schema = repository._inspect(cursor, expected, settings)
        report["schema_info"] = schema.model_dump(mode="json")
        report["inventory_unique_verified"] = ["inventory_number"] in schema.unique_keys
        if not schema.compatible or schema.columns.get("inventory_number") not in ("text", "character varying"):
            report["blockers"].append("Hiányzó, inkompatibilis séma vagy nem támogatott leltáriszám-típus.")
            report["migration_ready"] = False
            return report
        table = sql.Identifier(settings.target_schema, settings.target_table)
        cursor.execute(sql.SQL("""SELECT count(*),
            count(*) FILTER (WHERE inventory_number IS NULL),
            count(*) FILTER (WHERE inventory_number = ''),
            count(*) FILTER (WHERE inventory_number <> '' AND inventory_number ~ '^[[:space:]]*$'),
            count(*) FILTER (WHERE inventory_number ~ '[[:space:]]') FROM {}""").format(table))
        report["counts"] = dict(zip(("rows", "null", "empty", "whitespace_only", "contains_whitespace"), cursor.fetchone()))
        groups = sql.SQL("SELECT inventory_number, count(*) AS n FROM {} WHERE inventory_number IS NOT NULL GROUP BY inventory_number HAVING count(*) > 1").format(table)
        cursor.execute(sql.SQL("SELECT count(*), coalesce(sum(n), 0) FROM ({}) d").format(groups))
        group_count, affected = cursor.fetchone()
        report["duplicate_groups"] = group_count
        report["duplicate_rows"] = int(affected)
        cursor.execute(sql.SQL("{} ORDER BY n DESC, inventory_number LIMIT %s").format(groups), (sample_limit,))
        duplicates = cursor.fetchall()
        report["duplicate_samples_truncated"] = group_count > sample_limit
        report["duplicate_samples"] = []
        fields = [field for field in ("inventory_number", "item_code", "sub_code", "name", "location", "activation_date") if field in schema.columns]
        selected = sql.SQL(", ").join(map(sql.Identifier, fields))
        for number, count in duplicates:
            cursor.execute(sql.SQL("SELECT {} FROM {} WHERE inventory_number = %s ORDER BY {} LIMIT %s").format(selected, table, selected),
                           (number, sample_limit))
            report["duplicate_samples"].append({"inventory_number": number, "occurrence_count": count,
                "records": [{name: _scalar(value) for name, value in zip(fields, row)} for row in cursor.fetchall()],
                "records_truncated": count > sample_limit,
                "recommended_action": "Kézzel ellenőrizd az eredeti leltárbizonylatokat; ne töröld vagy számozd át automatikusan."})
        # Diagnostic grouping ONLY. This expression is never a lookup or a key.
        normalized = sql.SQL("""SELECT lower(regexp_replace(inventory_number, '[[:space:]]', '', 'g')) AS diagnostic_value,
            count(DISTINCT inventory_number) AS variants, count(*) AS n
            FROM {} WHERE inventory_number IS NOT NULL GROUP BY 1 HAVING count(DISTINCT inventory_number) > 1""").format(table)
        cursor.execute(sql.SQL("SELECT count(*) FROM ({}) d").format(normalized))
        report["normalization_collision_groups"] = cursor.fetchone()[0]
        cursor.execute(sql.SQL("{} ORDER BY diagnostic_value LIMIT %s").format(normalized), (sample_limit,))
        collisions = cursor.fetchall()
        report["normalization_collision_samples"] = []
        for value, variants, count in collisions:
            cursor.execute(sql.SQL("""SELECT DISTINCT inventory_number FROM {} WHERE
                lower(regexp_replace(inventory_number, '[[:space:]]', '', 'g')) = %s ORDER BY inventory_number LIMIT %s""").format(table), (value, sample_limit))
            report["normalization_collision_samples"].append({"diagnostic_value": value,
                "distinct_values": [row[0] for row in cursor.fetchall()], "variant_count": variants,
                "occurrence_count": count, "values_truncated": variants > sample_limit})
        report["normalization_collision_samples_truncated"] = len(collisions) < report["normalization_collision_groups"]
    if report["duplicate_groups"]:
        report["blockers"].append("Azonos nem NULL leltári számok: a teljes UNIQUE index nem hozható létre.")
    if report["counts"]["empty"] or report["counts"]["whitespace_only"]:
        report["blockers"].append("Üres vagy whitespace leltári szám: kézi adatminőség-ellenőrzés szükséges.")
    if report["counts"]["null"]:
        report["warnings"].append("A nullable UNIQUE több NULL értéket enged; ezekhez nincs leltáriszám-azonosítás.")
    if report["normalization_collision_groups"]:
        report["warnings"].append("Whitespace/kisbetűsítés után ütköző, nyersen különböző értékek; ne normalizáld őket automatikusan.")
    report["migration_ready"] = not report["blockers"]
    return report
