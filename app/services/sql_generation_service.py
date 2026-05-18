"""
Text-to-SQL generáló service.

Ez a modul sémakontextussal és felhasználói kérdéssel promptot készít, meghívja az LLM-et,
majd a kimenetet tiszta SQL stringgé utófeldolgozza.
"""

from app.services.llm_service import ask_llm
from app.services.schema_service import build_schema_text


def load_prompt() -> str:
    """A text-to-SQL promptsablon betöltése lemezről."""
    # A prompt a Python kódon kívül van, így a feldolgozási logika módosítása nélkül hangolható.
    with open("app/prompts/text_to_sql.txt", "r", encoding="utf-8") as f:
        return f.read()


def clean_sql(sql: str) -> str:
    """Markdown kódblokk-jelölések eltávolítása és környező üres karakterek levágása."""
    # Az LLM-ek néha Markdown blokkba teszik az SQL-t akkor is, ha ezt tiltjuk.
    # Ez eltávolítja a gyakori wrappereket validálás előtt.
    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    return sql.strip()


def generate_sql(question: str) -> str:
    """SQL generálása természetes nyelvű kérdésből, séma-alapú promptolással."""
    template = load_prompt()
    # A séma szöveg a modell egyetlen engedélyezett nézete az adatbázis szerkezetéről.
    schema = build_schema_text()

    # A prompt placeholderök kitöltése futásidejű sémával és felhasználói kérdéssel.
    prompt = template.format(
        schema=schema,
        question=question
    )

    raw_sql = ask_llm(prompt)
    # A tisztítás nem biztonsági ellenőrzés. Az orchestration layer validátora
    # továbbra is ellenőrzi futtatás előtt, hogy az SQL biztonságos-e.
    return clean_sql(raw_sql)
