"""
SQL validator that enforces a strict read-only query policy.

Accepted query types:
- SELECT
- WITH (CTE that ultimately resolves to a read-only query)
"""

import re


# Keywords that are never allowed in generated SQL because they can mutate data,
# alter schema, or invoke procedural execution.
BANNED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "MERGE", "CALL", "EXEC", "EXECUTE"
}


class SQLValidationError(Exception):
    """Raised when SQL does not satisfy the application's safety constraints."""



def validate_sql(sql: str) -> str:
    """
    Validate and normalize SQL before execution.

    Safety checks:
    - Non-empty input.
    - No SQL comments.
    - No multi-statement payload.
    - Must start with SELECT or WITH.
    - Must not contain banned write/DDL keywords.

    Returns:
    - Clean SQL string without trailing semicolon.
    """
    # Reject empty or whitespace-only SQL.
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL query.")

    # Normalize surrounding whitespace for consistent checks.
    normalized = sql.strip()

    # Disallow SQL comments to reduce obfuscation and payload smuggling risk.
    if "--" in normalized or "/*" in normalized or "*/" in normalized:
        raise SQLValidationError("SQL comments are not allowed.")

    # Reject multiple statements; only a single query is allowed.
    semicolon_count = normalized.count(";")
    if semicolon_count > 1:
        raise SQLValidationError("Multiple SQL statements are not allowed.")

    # Use uppercase copy for keyword-oriented checks.
    sql_upper = normalized.upper()

    # Enforce read-only query entry points.
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        raise SQLValidationError("Only SELECT queries are allowed.")

    # Block dangerous keywords even if the query starts with SELECT/WITH.
    for keyword in BANNED_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, sql_upper):
            raise SQLValidationError(f"Banned keyword detected: {keyword}")

    # Remove trailing semicolon to keep downstream handling consistent.
    return normalized.rstrip(";")
