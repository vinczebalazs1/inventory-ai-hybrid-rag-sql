import os
from dotenv import load_dotenv
from app.db.connection import get_connection

# Load .env values early so runtime limits can be configured without code changes.
load_dotenv()

# Maximum execution time for a single SQL statement in milliseconds.
# If a query exceeds this limit, PostgreSQL aborts it to protect the system.
QUERY_TIMEOUT_MS = int(os.getenv("SQL_QUERY_TIMEOUT_MS", "5000"))

# Maximum number of rows returned to the caller.
# This prevents very large result sets from consuming too much memory or bandwidth.
MAX_ROWS_RETURNED = int(os.getenv("SQL_MAX_ROWS_RETURNED", "100"))


def execute_query(sql: str) -> dict:
    """
    Execute a SQL statement and return a normalized dictionary payload.

    Return format:
    - columns: list of column names (empty for non-SELECT statements)
    - rows: list of row tuples (limited by MAX_ROWS_RETURNED)
    - row_count: number of rows included in `rows`

    Resource safety:
    - Cursor and connection are always closed in `finally`, even on errors.
    """
    # Open a new database connection for this execution request.
    conn = get_connection()
    # Create a cursor to send SQL commands and fetch data.
    cur = conn.cursor()

    try:
        # Enforce a per-statement timeout at the PostgreSQL session level.
        # This protects the application from hanging on expensive queries.
        cur.execute(f"SET statement_timeout = {QUERY_TIMEOUT_MS};")

        # Execute the caller-provided SQL statement.
        cur.execute(sql)

        # `cur.description` is None when the statement does not produce rows
        # (for example INSERT/UPDATE/DELETE without RETURNING).
        if cur.description is None:
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

        # Extract column names from cursor metadata.
        columns = [desc[0] for desc in cur.description]
        # Fetch only up to the configured row cap.
        rows = cur.fetchmany(MAX_ROWS_RETURNED)

        return {
            "columns": columns,
            "rows": rows,
            # Count rows that are actually returned (after limit is applied).
            "row_count": len(rows),
        }

    finally:
        # Always release database resources, regardless of success or failure.
        cur.close()
        conn.close()
