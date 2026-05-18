import os
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv
from app.errors import DatabaseUnavailableError

# A `.env` változókat már modul importkor betöltjük.
# Így a DB kapcsolati paraméterek elérhetők, mire a `get_connection` lefut.
load_dotenv()


def get_connection():
    """
    Új PostgreSQL kapcsolat létrehozása és visszaadása környezeti változókból.

    Elvárt környezeti változók:
    - DB_NAME: adatbázis neve
    - DB_USER: adatbázis felhasználó
    - DB_PASSWORD: adatbázis jelszó
    - DB_HOST: adatbázis host
    - DB_PORT: adatbázis port

    A függvény minden híváskor friss connection objektumot ad vissza.
    A kapcsolat életciklusát (nyitás/zárás) a hívó kezeli.
    """
    required_vars = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]
    # Korán, érthető üzenettel hibázunk, ha a .env hiányos. Enélkül a psycopg2
    # hibák kezdőknek sokkal nehezebben értelmezhetők.
    missing_vars = [name for name in required_vars if not os.getenv(name)]

    if missing_vars:
        raise DatabaseUnavailableError(
            "Az adatbázis kapcsolat még nincs beállítva. Ellenőrizd a DB_* értékeket a .env fájlban, majd indítsd újra az alkalmazást.",
            detail=f"Missing environment variables: {', '.join(missing_vars)}",
        )

    try:
        # Minden queryhez friss kapcsolat nyílik. Ez egyszerű és kis appnál rendben van,
        # productionben viszont általában connection poolt használnánk.
        return psycopg2.connect(
            # Az adatbázis neve, amelyhez kapcsolódunk.
            dbname=os.getenv("DB_NAME"),
            # Az autentikációhoz használt felhasználónév.
            user=os.getenv("DB_USER"),
            # Az autentikációhoz használt jelszó.
            password=os.getenv("DB_PASSWORD"),
            # Host vagy IP, ahol a PostgreSQL fut.
            host=os.getenv("DB_HOST"),
            # A PostgreSQL által nyitott TCP port, általában 5432.
            port=os.getenv("DB_PORT"),
        )
    except OperationalError as exc:
        # Az OperationalError tipikus kapcsolat/auth/hálózati hibákat fed le.
        raise DatabaseUnavailableError(
            "Az alkalmazás nem tud kapcsolódni az adatbázishoz. Ellenőrizd, hogy fut-e a PostgreSQL, és helyesek-e a DB_* beállítások.",
            detail=str(exc),
        ) from exc
