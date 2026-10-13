"""Comparison forms; identifiers are never case-folded or stripped of punctuation."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from app.document_processing.validation_service import normalize
from .config import IDENTIFIER_FIELDS
from .models import Scalar


def text_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def identifier_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def comparison_value(value: Scalar, dtype: str, field: str) -> Scalar:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a supported inventory value")
    if field in {"purchase_value", "depreciation", "current_value"} and isinstance(value, float):
        raise ValueError("Financial values require an integer or exact decimal string")
    if field in IDENTIFIER_FIELDS:
        if not isinstance(value, str):
            raise ValueError("Identifier must retain its original text representation")
        return identifier_key(value)
    dtype = dtype.lower()
    if dtype in {"integer", "bigint", "smallint"} or any(
        token in dtype for token in ("numeric", "decimal", "real", "double", "float")
    ):
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("Expected a canonical numeric value") from exc
        if not number.is_finite():
            raise ValueError("Expected a finite numeric value")
        if dtype in {"integer", "bigint", "smallint"}:
            if number != number.to_integral_value():
                raise ValueError("Expected an integer")
            return int(number)
        canonical = format(number, "f")
        return "0" if number == 0 else canonical.rstrip("0").rstrip(".") if "." in canonical else canonical
    if dtype == "date":
        return date.fromisoformat(str(value)).isoformat()
    if field == "currency":
        return normalize(str(value), dtype, field)
    if not isinstance(value, str):
        raise ValueError("Expected text")
    return text_key(value)


def raw_comparison_value(value: str, dtype: str, field: str) -> Scalar:
    return comparison_value(normalize(value, dtype, field), dtype, field)


def model_tokens(value: str) -> frozenset[str]:
    """Digit-bearing tokens retain letters and dashes (5540 != 5550, X1 != X2)."""
    return frozenset(token for token in re.findall(r"[\w]+(?:[-./][\w]+)*", text_key(value))
                     if any(char.isdigit() for char in token))


def model_conflict(left: str, right: str) -> bool:
    left_tokens, right_tokens = model_tokens(left), model_tokens(right)
    return bool(left_tokens and right_tokens and left_tokens != right_tokens)
