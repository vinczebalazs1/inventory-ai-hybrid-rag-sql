"""CSV uses the same result objects as the UI; protect spreadsheet formulas."""
import csv
import io
import json


def csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    columns = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return stream.getvalue().encode("utf-8-sig")


def reconciliation_rows(result, kind: str) -> list[dict]:
    groups = result.group_results or [result]
    rows = []
    for group in groups:
        values = (group.prepared_document.fields if group.prepared_document else []) if kind == "fields" else (
            group.candidates if kind == "candidates" else group.field_comparisons)
        for value in values:
            row = value.model_dump(mode="json")
            row["asset_group_id"] = group.asset_group_id
            rows.append(row)
    if kind == "fields":
        for value in result.unassigned_fields:
            rows.append({**value.model_dump(mode="json"), "asset_group_id": None, "grouping_status": "UNASSIGNED"})
    return rows
