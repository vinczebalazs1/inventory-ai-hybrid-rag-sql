"""
Fő orchestration flow a felhasználói kérdések route-olásához és megválaszolásához.
"""

from typing import List
from app.security.injection_checks import check_prompt_injection
from app.security.injection_checks import PromptInjectionError
from app.services.routing_service import route_query
from app.services.sql_generation_service import generate_sql
from app.security.sql_validator import validate_sql
from app.security.guardrails import ensure_limit
from app.db.executor import execute_query
from app.services.answer_service import generate_natural_answer
from app.rag.retrieval.rag_service import answer_rag_details, answer_hybrid_details
from app.errors import AppError, UserInputError


NAME_COLUMN_HINTS = {
    "name",
    "device",
    "device_name",
    "item",
    "item_name",
    "equipment",
    "equipment_name",
    "asset",
    "asset_name",
}


def _run_sql_pipeline(question: str) -> tuple[str, dict]:
    """
    SQL generálása, validálása és futtatása egy kérdéshez.
    """
    # Az LLM kimenetét nem tekintjük megbízhatónak. Validáción és guardrailokon
    # kell átmennie, mielőtt eljut az adatbázis executorhoz.
    raw_sql = generate_sql(question)
    validated_sql = validate_sql(raw_sql)
    safe_sql = ensure_limit(validated_sql)
    result = execute_query(safe_sql)
    return safe_sql, result


def _extract_names_from_sql_result(result: dict) -> List[str]:
    """
    Lehetséges entitásnevek kinyerése SQL eredménysorokból HYBRID visszakereséshez.
    """
    columns = result.get("columns", []) or []
    rows = result.get("rows", []) or []

    if not columns or not rows:
        return []

    # A HYBRID visszakeresésnek eszköz/item nevekre van szüksége. Abból következtetünk
    # a név oszlopokra, hogy ismert neveket és a gyakori *_name konvenciót nézzük.
    name_indexes = []
    for idx, col in enumerate(columns):
        normalized = str(col).strip().lower()
        if normalized in NAME_COLUMN_HINTS or normalized.endswith("_name"):
            name_indexes.append(idx)

    if not name_indexes:
        return []

    names = []
    for row in rows:
        for idx in name_indexes:
            if idx < len(row):
                value = row[idx]
                if isinstance(value, str) and value.strip():
                    names.append(value.strip().lower())

    return sorted(set(names))


def handle_question(question: str) -> dict:
    """
    A kérdés SQL, RAG vagy HYBRID flow-ba irányítása és egységes válaszcsomag visszaadása.
    """
    try:
        # 1. Blokkoljuk az egyértelműen veszélyes promptokat, mielőtt az LLM látná a kérdést.
        check_prompt_injection(question)
        # 2. Megkérdezzük az útvonalválasztót, melyik feldolgozási lánc kezelje a kérdést.
        route = route_query(question)

        if route == "RAG":
            # Tiszta dokumentációs flow: nem generálunk és nem futtatunk SQL-t.
            rag_response = answer_rag_details(question)
            return {
                "ok": True,
                "question": question,
                "route": route,
                "sql": None,
                "result": {"columns": [], "rows": [], "row_count": 0},
                "answer": rag_response["answer"],
                "matched_names": [],
                "sources": rag_response["sources"],
            }

        # Az SQL és a HYBRID ág is ugyanazzal az SQL feldolgozási lánccal indul.
        safe_sql, result = _run_sql_pipeline(question)

        if route == "SQL":
            # Csak SQL flow: a végső válasz kizárólag DB eredményre épül.
            answer = generate_natural_answer(question, safe_sql, result)
            return {
                "ok": True,
                "question": question,
                "route": route,
                "sql": safe_sql,
                "result": result,
                "answer": answer,
                "matched_names": [],
                "sources": [],
            }

        # HYBRID flow: felhasználjuk az SQL tényeket, majd hozzájuk keresünk dokumentációt.
        matched_names = _extract_names_from_sql_result(result)
        rag_response = answer_hybrid_details(question, matched_names, result)

        return {
            "ok": True,
            "question": question,
            "route": "HYBRID",
            "sql": safe_sql,
            "result": result,
            "answer": rag_response["answer"],
            "matched_names": matched_names,
            "sources": rag_response["sources"],
        }
    except PromptInjectionError as exc:
        # Az input-biztonsági hibák a felhasználó által javíthatók, ezért konkrét,
        # barátságos üzenetet kapnak generikus backend hiba helyett.
        error = UserInputError(
            "A kérdés úgy tűnik, mintha nem biztonságos utasítást tartalmazna. Kérlek csak leltáradatokról vagy eszközinformációkról kérdezz.",
            detail=str(exc),
        )
    except AppError as exc:
        # Az AppError leszármazottak már biztonságos, UI-ban mutatható üzeneteket tartalmaznak.
        error = exc
    except Exception as exc:
        # Utolsó védőháló: a váratlan exceptionök generikus üzenet mögé kerülnek,
        # a részletek pedig csak hibakeresési módban láthatók.
        error = AppError(
            "Az alkalmazás váratlan hibába futott a kérdés feldolgozása közben. Próbáld újra, vagy nézd meg a debug részleteket.",
            title="A kérés nem teljesíthető",
            code="UNEXPECTED_ERROR",
            detail=str(exc),
        )

    return {
        "ok": False,
        "question": question,
        "route": "-",
        "sql": None,
        "result": {"columns": [], "rows": [], "row_count": 0},
        "answer": None,
        "matched_names": [],
        "sources": [],
        "error": error.to_dict(),
    }
