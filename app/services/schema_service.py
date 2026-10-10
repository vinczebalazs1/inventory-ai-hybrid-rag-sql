"""
Séma metaadat betöltő és formázó modul.

Ez a modul config fájlokból olvassa ki a séma struktúrát és az opcionális
emberi leírásokat, majd egyetlen szövegblokkot készít LLM prompt kondicionáláshoz.
"""

import json
from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def load_schema() -> dict:
    """Nyers tábla/oszlop struktúra betöltése JSON konfigurációból."""
    with (CONFIG_DIR / "schema.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def load_descriptions() -> dict:
    """Opcionális tábla/oszlop leírások betöltése YAML konfigurációból."""
    with (CONFIG_DIR / "schema_descriptions.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_schema_text() -> str:
    """
    Olvasható sémaösszefoglaló string építése a text-to-SQL prompthoz.

    A kimeneti forma táblánként csoportosít, majd oszlopokat listáz típusokkal
    és opcionális természetes nyelvű leírásokkal.
    """
    schema = load_schema()
    desc = load_descriptions()

    text = ""

    # Itt készül az LLM számára olvasható séma blokk. A modell nem kérdezi le
    # közvetlenül a DB metaadatokat, hanem erre a generált szövegre támaszkodik.
    # Végigmegyünk az ismert táblákon, és hozzáadjuk az opcionális leírásokat.
    for table, columns in schema.items():
        text += f"\nTable: {table}\n"

        table_desc = desc.get(table, {}).get("description", "")
        if table_desc:
            text += f"Description: {table_desc}\n"

        text += "Columns:\n"

        # Minden oszlopot bullet sorba renderelünk, hogy a modell könnyebben értelmezze.
        for col in columns:
            name = col["column"]
            dtype = col["type"]

            col_desc = desc.get(table, {}).get("columns", {}).get(name, "")

            # Az oszlopleírások üzleti jelentést adnak az amúgy kétértelmű mezőknek,
            # ami segít az LLM-nek jobb SQL-t generálni.
            line = f"- {name} ({dtype})"
            if col_desc:
                line += f": {col_desc}"

            text += line + "\n"

    return text
