"""
SQL safety guardrails focused on result-size limiting.

This module ensures generated queries always have a row limit and that
user-provided limits cannot exceed the configured maximum.
"""

import os
import re
from dotenv import load_dotenv

# Load runtime limits from environment variables.
load_dotenv()

# Default limit added when query has no explicit LIMIT clause.
DEFAULT_LIMIT = int(os.getenv("SQL_DEFAULT_LIMIT", "50"))
# Hard upper bound for any LIMIT value.
MAX_LIMIT = int(os.getenv("SQL_MAX_LIMIT", "200"))


def normalize_sql(sql: str) -> str:
    """Collapse repeated whitespace to simplify downstream pattern matching."""
    return " ".join(sql.split())


def has_limit(sql: str) -> bool:
    """Return True when SQL contains an explicit numeric LIMIT clause."""
    return re.search(r"\bLIMIT\s+\d+\b", sql, re.IGNORECASE) is not None


def ensure_limit(sql: str) -> str:
    """
    Guarantee a safe LIMIT in the SQL statement.

    Behavior:
    - If LIMIT exists and is <= MAX_LIMIT, keep it unchanged.
    - If LIMIT exists and is > MAX_LIMIT, clamp it down to MAX_LIMIT.
    - If LIMIT does not exist, append LIMIT DEFAULT_LIMIT.
    """
    normalized = normalize_sql(sql)

    if has_limit(normalized):
        # Extract the current LIMIT value to decide whether clamping is needed.
        match = re.search(r"\bLIMIT\s+(\d+)\b", normalized, re.IGNORECASE)
        if match:
            current_limit = int(match.group(1))
            if current_limit > MAX_LIMIT:
                # Replace oversized LIMIT with the configured safe maximum.
                normalized = re.sub(
                    r"\bLIMIT\s+\d+\b",
                    f"LIMIT {MAX_LIMIT}",
                    normalized,
                    flags=re.IGNORECASE
                )
        return normalized

    # Append a default LIMIT when no limit is present.
    return f"{normalized} LIMIT {DEFAULT_LIMIT}"
