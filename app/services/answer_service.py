"""
Natural-language answer generation from SQL execution results.

This module converts structured query output into a user-facing response by
feeding question, SQL, and result payload into an answer-generation prompt.
"""

import json
from app.services.llm_service import ask_llm


def load_answer_prompt() -> str:
    """Load the answer-generation prompt template from disk."""
    with open("app/prompts/answer_generation.txt", "r", encoding="utf-8") as f:
        return f.read()


def generate_natural_answer(question: str, sql: str, result: dict) -> str:
    """
    Generate a human-readable answer from the database result payload.

    If no rows are returned, respond with a friendly fallback message.
    """
    # Short-circuit when the query returned no data.
    if result["row_count"] == 0:
        return "I could not find data matching your question."

    # Load prompt template and inject runtime context values.
    prompt_template = load_answer_prompt()

    prompt = prompt_template.format(
        question=question,
        sql=sql,
        # Keep Unicode characters in result data and pretty-print for clarity.
        result=json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )

    # Return cleaned model output.
    return ask_llm(prompt).strip()
