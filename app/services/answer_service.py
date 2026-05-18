"""
Természetes nyelvű válaszgenerálás SQL futtatási eredményekből.

Ez a modul a strukturált query kimenetet felhasználói válasszá alakítja úgy,
hogy a kérdést, SQL-t és result válaszcsomagot válaszgeneráló promptba teszi.
"""

import json
from app.services.llm_service import ask_llm


def load_answer_prompt() -> str:
    """A válaszgeneráló promptsablon betöltése lemezről."""
    with open("app/prompts/answer_generation.txt", "r", encoding="utf-8") as f:
        return f.read()


def generate_natural_answer(question: str, sql: str, result: dict) -> str:
    """
    Ember által olvasható válasz generálása az adatbázis result válaszcsomagból.

    Ha nincs visszaadott sor, barátságos fallback üzenetet adunk.
    """
    # Rövidre zárjuk, ha a lekérdezés nem adott vissza adatot.
    # Így nem költünk LLM hívást arra, hogy csak annyit mondjon: nincs találat.
    if result["row_count"] == 0:
        return "I could not find data matching your question."

    # Betöltjük a promptsablont, majd behelyettesítjük a futásidejű kontextust.
    prompt_template = load_answer_prompt()

    prompt = prompt_template.format(
        question=question,
        sql=sql,
        # Megtartjuk a Unicode karaktereket és szépen formázzuk az eredményt.
        # A default=str kezeli azokat a dátumokat/decimálisokat/tuple-öket,
        # amelyeket a json alapból nem tudna szerializálni.
        result=json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )

    # A megtisztított modellkimenetet adjuk vissza.
    return ask_llm(prompt).strip()
