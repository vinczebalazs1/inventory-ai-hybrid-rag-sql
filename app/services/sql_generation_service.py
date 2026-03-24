"""
Text-to-SQL generation service.

This module prepares a prompt with schema context and user question, calls the
LLM, and post-processes the result into a clean SQL string.
"""

from app.services.llm_service import ask_llm
from app.services.schema_service import build_schema_text


def load_prompt() -> str:
    """Load the text-to-SQL prompt template from disk."""
    with open("app/prompts/text_to_sql.txt", "r", encoding="utf-8") as f:
        return f.read()


def clean_sql(sql: str) -> str:
    """Remove Markdown code fences and trim surrounding whitespace."""
    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    return sql.strip()


def generate_sql(question: str) -> str:
    """Generate SQL from a natural-language question using schema-aware prompting."""
    template = load_prompt()
    schema = build_schema_text()

    # Fill prompt placeholders with runtime schema and user question.
    prompt = template.format(
        schema=schema,
        question=question
    )

    raw_sql = ask_llm(prompt)
    return clean_sql(raw_sql)
