"""Bounded deterministic candidate selection; it never assigns record identity."""
import re

from rapidfuzz.fuzz import ratio, token_sort_ratio

from .config import IDENTIFIER_FIELDS, MatchingSettings
from .models import DatabaseRecord, Scalar


def _text(value: Scalar) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def name_similarity(left: Scalar, right: Scalar) -> float:
    """Full-string similarity avoids partial/subsequence-only perfect matches."""
    a, b = _text(left), _text(right)
    return max(ratio(a, b), token_sort_ratio(a, b)) / 100.0 if a and b else 0.0


def candidate_priority(record: DatabaseRecord, values: dict[str, Scalar]) -> tuple:
    exact = sum(values.get(key) is not None and values[key] == record.values.get(key)
                for key in IDENTIFIER_FIELDS)
    composite = bool(values.get("item_code") is not None and
                     values.get("sub_code") is not None and
                     values["item_code"] == record.values.get("item_code") and
                     values["sub_code"] == record.values.get("sub_code"))
    inventory = bool(values.get("inventory_number") and values["inventory_number"] == record.values.get("inventory_number"))
    return inventory, exact, composite, name_similarity(values.get("name"), record.values.get("name"))


def select_candidates(
    records: list[DatabaseRecord], values: dict[str, Scalar], settings: MatchingSettings,
) -> tuple[list[DatabaseRecord], bool]:
    """Preserve duplicate rows; pruning is declared separately from retrieval scope."""
    import json
    relevant = []
    for record in records:
        priority = candidate_priority(record, values)
        if priority[1] or (settings.strategy == "hybrid" and priority[3] >= settings.duplicate_threshold):
            relevant.append(record)
    relevant.sort(key=lambda record: (
        *(-float(value) for value in candidate_priority(record, values)),
        record.record_id or "",
        json.dumps(record.values, sort_keys=True, ensure_ascii=False),
    ))
    return relevant[:settings.max_candidates], len(relevant) > settings.max_candidates


def fuzzy_tokens(value: str) -> list[str]:
    """A bounded SQL prefilter, explicitly not an exhaustive typo search."""
    tokens = set(re.findall(r"[^\W_]+", _text(value), flags=re.UNICODE))
    return sorted((token for token in tokens if len(token) >= 2), key=lambda token: (-len(token), token))[:8]


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
