"""
SQL validátor, amely szigorú read-only query szabályt kényszerít ki.

Elfogadott query típusok:
- SELECT
- WITH, ha végül read-only queryként fut
"""

import re


# Kulcsszavak, amelyek generált SQL-ben soha nem engedélyezettek, mert adatot
# módosíthatnak, sémát változtathatnak, vagy procedurális futtatást indíthatnak.
BANNED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "MERGE", "CALL", "EXEC", "EXECUTE"
}


class SQLValidationError(Exception):
    """Akkor dobjuk, ha az SQL nem felel meg az alkalmazás biztonsági szabályainak."""


def validate_sql(sql: str) -> str:
    """
    SQL validálása és normalizálása futtatás előtt.

    Biztonsági ellenőrzések:
    - Nem lehet üres.
    - Nem tartalmazhat SQL kommenteket.
    - Nem tartalmazhat több utasításból álló terhelést.
    - SELECT vagy WITH kezdetűnek kell lennie.
    - Nem tartalmazhat tiltott író/DDL kulcsszavakat.

    Visszatérés:
    - Tiszta SQL string záró pontosvessző nélkül.
    """
    # Üres vagy csak üres karakterekből álló SQL elutasítása.
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL query.")

    # Környező üres karakterek normalizálása következetes ellenőrzésekhez.
    normalized = sql.strip()

    # SQL kommentek tiltása az obfuszkáció és payload-csempészés kockázatának csökkentésére.
    if "--" in normalized or "/*" in normalized or "*/" in normalized:
        raise SQLValidationError("SQL comments are not allowed.")

    # Több utasítás elutasítása; csak egyetlen query engedélyezett.
    semicolon_count = normalized.count(";")
    if semicolon_count > 1:
        raise SQLValidationError("Multiple SQL statements are not allowed.")

    # Nagybetűs másolat használata kulcsszó-alapú ellenőrzésekhez.
    sql_upper = normalized.upper()

    # Csak olvasó query belépési pontok engedélyezése.
    # A WITH engedélyezett, mert a read-only CTE hasznos komplexebb SELECT-ekhez.
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        raise SQLValidationError("Only SELECT queries are allowed.")

    # Veszélyes kulcsszavak blokkolása akkor is, ha a query SELECT/WITH-tel indul.
    # Ez string-szintű védelem, nem teljes SQL parser, de megfogja az LLM által
    # generált legnyilvánvalóbb romboló parancsokat.
    for keyword in BANNED_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, sql_upper):
            raise SQLValidationError(f"Banned keyword detected: {keyword}")

    # Záró pontosvessző eltávolítása, hogy a későbbi kezelés egységes maradjon.
    return normalized.rstrip(";")
