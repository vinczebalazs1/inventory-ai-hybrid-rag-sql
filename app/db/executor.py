import os
import psycopg2
from dotenv import load_dotenv
from app.db.connection import get_connection
from app.errors import DatabaseUnavailableError

# Korán betöltjük a .env értékeket, hogy a futási limitek kódmódosítás nélkül állíthatók legyenek.
load_dotenv()

# Egyetlen SQL utasítás maximális futási ideje milliszekundumban.
# Ha a lekérdezés túllépi ezt, a PostgreSQL megszakítja a rendszer védelme érdekében.
QUERY_TIMEOUT_MS = int(os.getenv("SQL_QUERY_TIMEOUT_MS", "5000"))

# A callernek visszaadott sorok maximális száma.
# Ez megakadályozza, hogy nagyon nagy eredményhalmazok túl sok memóriát vagy sávszélt fogyasszanak.
MAX_ROWS_RETURNED = int(os.getenv("SQL_MAX_ROWS_RETURNED", "100"))


def execute_query(sql: str) -> dict:
    """
    SQL utasítás futtatása és normalizált dictionary válaszcsomag visszaadása.

    Visszatérési forma:
    - columns: oszlopnevek listája
    - rows: sor tuple-ök listája, MAX_ROWS_RETURNED által limitálva
    - row_count: a `rows` mezőben ténylegesen szereplő sorok száma

    Erőforrás-biztonság:
    - A cursor és connection mindig bezáródik a `finally` blokkban, hiba esetén is.
    """
    conn = None
    cur = None

    try:
        # Új adatbázis kapcsolat nyitása ehhez az execution requesthez.
        conn = get_connection()
        # Cursor létrehozása SQL parancsok küldéséhez és adatok lekéréséhez.
        cur = conn.cursor()

        # Statement szintű timeout beállítása a PostgreSQL sessionben.
        # Ez megvédi az alkalmazást a drága lekérdezéseken való beragadástól.
        cur.execute(f"SET statement_timeout = {QUERY_TIMEOUT_MS};")

        # A caller által adott SQL utasítás futtatása.
        # Ekkorra az orchestratornak már validálnia és limitálnia kellett az SQL-t,
        # így az executor csak az adatbázis interakcióra koncentrál.
        cur.execute(sql)

        # A `cur.description` None, ha az utasítás nem ad vissza sorokat
        # (például INSERT/UPDATE/DELETE RETURNING nélkül). Nálunk ez most még nem használt eset.
        if cur.description is None:
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

        # Oszlopnevek kinyerése a cursor metaadataiból.
        columns = [desc[0] for desc in cur.description]
        # Csak a konfigurált sorkorlátig kérünk le adatot.
        # Ez a második védelmi réteg az SQL LIMIT guardrail után.
        rows = cur.fetchmany(MAX_ROWS_RETURNED)

        return {
            "columns": columns,
            "rows": rows,
            # A ténylegesen visszaadott sorok száma a limit alkalmazása után.
            "row_count": len(rows),
        }

    except DatabaseUnavailableError:
        # Ezt a connection layer már barátságos DB hibává alakította.
        raise
    except psycopg2.Error as exc:
        # A query-szintű DB hibák, például hiányzó oszlop vagy timeout, szintén
        # adatbázis elérhetőségi/futtatási problémaként jelennek meg a UI-ban.
        raise DatabaseUnavailableError(
            "Az adatbázis nem tudta lefuttatni a lekérdezést. Ellenőrizd az adatbázis állapotát és a sémát, majd próbáld újra.",
            detail=str(exc),
        ) from exc
    finally:
        # Mindig felszabadítjuk az adatbázis erőforrásokat, siker és hiba esetén is.
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
