import os
import json
import psycopg2
from dotenv import load_dotenv

load_dotenv()

QUERY = """
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
"""


def main():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )

    cur = conn.cursor()
    cur.execute(QUERY)
    rows = cur.fetchall()

    schema = {}

    for table, column, dtype in rows:
        if table not in schema:
            schema[table] = []

        schema[table].append({
            "column": column,
            "type": dtype
        })

    os.makedirs("config", exist_ok=True)

    with open("config/schema.json", "w") as f:
        json.dump(schema, f, indent=2)

    print("✅ schema.json létrehozva")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()