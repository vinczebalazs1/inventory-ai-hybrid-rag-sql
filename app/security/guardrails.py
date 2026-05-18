"""
SQL biztonsági guardrailok az eredményhalmaz méretének korlátozására.

Ez a modul biztosítja, hogy a generált lekérdezésekben mindig legyen sorkorlát,
és a felhasználó/modell által adott limitek ne léphessék túl a konfigurált maximumot.
"""

import os
import re
from dotenv import load_dotenv

# Futásidejű limitek betöltése környezeti változókból.
load_dotenv()

# Alapértelmezett limit, amelyet akkor adunk hozzá, ha a queryben nincs explicit LIMIT.
DEFAULT_LIMIT = int(os.getenv("SQL_DEFAULT_LIMIT", "50"))
# Kemény felső korlát bármilyen LIMIT értékre.
MAX_LIMIT = int(os.getenv("SQL_MAX_LIMIT", "200"))


def normalize_sql(sql: str) -> str:
    """Ismétlődő üres karakterek összevonása a későbbi mintakeresés egyszerűsítéséhez."""
    return " ".join(sql.split())


def has_limit(sql: str) -> bool:
    """True értéket ad vissza, ha az SQL explicit numerikus LIMIT záradékot tartalmaz."""
    return re.search(r"\bLIMIT\s+\d+\b", sql, re.IGNORECASE) is not None


def ensure_limit(sql: str) -> str:
    """
    Biztonságos LIMIT garantálása az SQL utasításban.

    Viselkedés:
    - Ha van LIMIT és <= MAX_LIMIT, változatlanul hagyjuk.
    - Ha van LIMIT és > MAX_LIMIT, visszavágjuk MAX_LIMIT értékre.
    - Ha nincs LIMIT, hozzáadjuk a DEFAULT_LIMIT-et.
    """
    normalized = normalize_sql(sql)

    if has_limit(normalized):
        # A felhasználó/modell által adott LIMIT-et csak akkor tartjuk meg, ha az appban
        # konfigurált kemény maximum alatt van.
        # Kinyerjük az aktuális LIMIT értéket, hogy eldöntsük, kell-e visszavágni.
        match = re.search(r"\bLIMIT\s+(\d+)\b", normalized, re.IGNORECASE)
        if match:
            current_limit = int(match.group(1))
            if current_limit > MAX_LIMIT:
                # A túl nagy LIMIT-et lecseréljük a konfigurált biztonságos maximumra.
                normalized = re.sub(
                    r"\bLIMIT\s+\d+\b",
                    f"LIMIT {MAX_LIMIT}",
                    normalized,
                    flags=re.IGNORECASE
                )
        return normalized

    # Alapértelmezett LIMIT hozzáadása, ha nincs limit.
    # Ez védi a UI-t és az adatbázist a véletlenül túl nagy eredményhalmazoktól.
    return f"{normalized} LIMIT {DEFAULT_LIMIT}"
