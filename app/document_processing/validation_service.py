"""Conservative normalization using schema types; raw data is never dropped."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
import re

from .models import MappingResult, ValidationIssue

logger = logging.getLogger(__name__)
CURRENCIES = {"huf": "HUF", "ft": "HUF", "forint": "HUF", "eur": "EUR",
              "€": "EUR", "euro": "EUR", "usd": "USD", "gbp": "GBP", "£": "GBP",
              "chf": "CHF", "jpy": "JPY", "cad": "CAD", "aud": "AUD"}


def number(value: str) -> Decimal:
    value = value.strip().translate(str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2212": "-"}))
    if " " in value:
        if not re.fullmatch(r"[+-]?\d{1,3}(?: \d{3})+(?:[.,]\d+)?", value):
            raise ValueError("Invalid digit grouping")
        value = value.replace(" ", "")
    if "," in value and "." in value:
        separator = "," if value.rfind(",") > value.rfind(".") else "."
        group = "." if separator == "," else ","
        if not re.fullmatch(r"[+-]?\d{1,3}(?:" + re.escape(group) + r"\d{3})+" + re.escape(separator) + r"\d+", value):
            raise ValueError("Invalid digit grouping")
        value = value.replace(group, "").replace(separator, ".")
    elif re.fullmatch(r"[+-]?\d{1,3}[.,]\d{3}", value):
        raise ValueError("Ambiguous decimal/thousands separator")
    else:
        value = value.replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        raise ValueError("Expected a number")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("Expected a finite number")
    return result


def normalize(value: str, dtype: str, field: str) -> str | int:
    value = value.strip()
    if not value:
        raise ValueError("Empty value")
    if field == "currency":
        if value.casefold() not in CURRENCIES:
            raise ValueError("Unknown or ambiguous currency; use an explicit supported code")
        return CURRENCIES[value.casefold()]
    if dtype == "date":
        # Spaces around the Hungarian date separators are presentation only.
        if re.fullmatch(r"\d{4}\.\s*\d{2}\.\s*\d{2}\.?", value):
            value = re.sub(r"\s+", "", value)
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y.%m.%d.", "%Y/%m/%d", "%d.%m.%Y", "%d.%m.%Y."):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                pass
        raise ValueError("Unrecognized or ambiguous date; use YYYY-MM-DD")
    if (field in {"purchase_value", "depreciation", "current_value"}
            and (dtype.lower() in {"integer", "bigint", "smallint"}
                 or any(name in dtype.lower() for name in ("numeric", "decimal", "real", "double", "float")))):
        # Strip only a separate, terminal Ft unit. Keep the amount's grouping
        # and sign intact for number(); raw_value/evidence remain unchanged.
        value = re.sub(r"(?<=\d)[ \u00a0\u202f\u2009]+(?:Ft|HUF)$", "", value, flags=re.IGNORECASE)
    if field == "quantity":
        value = re.sub(r"(?<=\d)[ \u00a0\u202f\u2009]*(?:db|darab)$", "", value, flags=re.IGNORECASE)
    if field == "location" and re.fullmatch(r"[A-ZÁÉÍÓÖŐÚÜŰ0-9_-]+\s+location", value):
        # Only a capitalized location code followed by this explicit field label.
        value = value.rsplit(None, 1)[0]
    if dtype.lower() in {"integer", "bigint", "smallint"}:
        parsed = number(value)
        if parsed != parsed.to_integral_value():
            raise ValueError("Expected an integer")
        return int(parsed)
    if any(name in dtype.lower() for name in ("numeric", "decimal", "real", "double", "float")):
        return format(number(value), "f")  # Preserve decimal precision in JSON.
    return value


def validate_fields(mapping: MappingResult, columns: list[dict]) -> list[ValidationIssue]:
    types = {column["column"]: column["type"] for column in columns}
    issues = []
    for index, field in enumerate(mapping.mapped_fields):
        field.occurrence_id = field.occurrence_id or f"field-{index + 1}"
        field.normalized_value = None
        raw = field.raw_value.strip().casefold()
        if not raw or raw in {"null", "none"}:
            field.normalization_status = "MISSING"
            continue
        if raw in {"nem ismert", "ismeretlen", "unknown", "not known"}:
            field.normalization_status = "EXPLICIT_UNKNOWN"
            continue
        try:
            field.normalized_value = normalize(field.raw_value, types[field.target_field], field.target_field)
            field.normalization_status = "VALID"
        except (ValueError, InvalidOperation, KeyError) as exc:
            field.normalization_status = "UNPARSEABLE" if str(exc) == "Expected a number" else "INVALID"
            issues.append(ValidationIssue(field=field.target_field, severity="warning", message=str(exc),
                occurrence_id=field.occurrence_id, raw_value=field.raw_value, page=field.page))
    logger.info("Validation completed: issues=%d", len(issues))
    return issues
