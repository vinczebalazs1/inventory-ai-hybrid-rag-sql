"""
Main orchestration flow for routing and answering user questions.
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
from app.rag.retrieval.rag_service import answer_rag, answer_hybrid
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
    Generate, validate, and execute SQL for a question.
    """
    raw_sql = generate_sql(question)
    validated_sql = validate_sql(raw_sql)
    safe_sql = ensure_limit(validated_sql)
    result = execute_query(safe_sql)
    return safe_sql, result


def _extract_names_from_sql_result(result: dict) -> List[str]:
    """
    Extract candidate entity names from SQL result rows for HYBRID retrieval.
    """
    columns = result.get("columns", []) or []
    rows = result.get("rows", []) or []

    if not columns or not rows:
        return []

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
    Route question to SQL, RAG, or HYBRID flow and return a uniform payload.
    """
    try:
        check_prompt_injection(question)
        route = route_query(question)

        if route == "RAG":
            answer = answer_rag(question)
            return {
                "ok": True,
                "question": question,
                "route": route,
                "sql": None,
                "result": {"columns": [], "rows": [], "row_count": 0},
                "answer": answer,
                "matched_names": [],
            }

        safe_sql, result = _run_sql_pipeline(question)

        if route == "SQL":
            answer = generate_natural_answer(question, safe_sql, result)
            return {
                "ok": True,
                "question": question,
                "route": route,
                "sql": safe_sql,
                "result": result,
                "answer": answer,
                "matched_names": [],
            }

        matched_names = _extract_names_from_sql_result(result)
        answer = answer_hybrid(question, matched_names, result)

        return {
            "ok": True,
            "question": question,
            "route": "HYBRID",
            "sql": safe_sql,
            "result": result,
            "answer": answer,
            "matched_names": matched_names,
        }
    except PromptInjectionError as exc:
        error = UserInputError(
            "A kérdés úgy tűnik, mintha nem biztonságos utasítást tartalmazna. Kérlek csak leltáradatokról vagy eszközinformációkról kérdezz.",
            detail=str(exc),
        )
    except AppError as exc:
        error = exc
    except Exception as exc:
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
        "error": error.to_dict(),
    }
