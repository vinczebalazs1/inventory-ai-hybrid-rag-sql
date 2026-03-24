"""
Schema metadata loader and formatter.

This module reads schema structure and optional human descriptions from config
files, then composes a single text block for LLM prompt conditioning.
"""

import json
import yaml


def load_schema() -> dict:
    """Load raw table/column structure from JSON configuration."""
    with open("config/schema.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_descriptions() -> dict:
    """Load optional table/column descriptions from YAML configuration."""
    with open("config/schema_descriptions.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_schema_text() -> str:
    """
    Build a readable schema summary string for the text-to-SQL prompt.

    Output format groups information by table, then lists columns with types
    and optional natural-language descriptions.
    """
    schema = load_schema()
    desc = load_descriptions()

    text = ""

    # Iterate all known tables and attach optional descriptions.
    for table, columns in schema.items():
        text += f"\nTable: {table}\n"

        table_desc = desc.get(table, {}).get("description", "")
        if table_desc:
            text += f"Description: {table_desc}\n"

        text += "Columns:\n"

        # Render each column as a bullet line for easier model parsing.
        for col in columns:
            name = col["column"]
            dtype = col["type"]

            col_desc = desc.get(table, {}).get("columns", {}).get(name, "")

            line = f"- {name} ({dtype})"
            if col_desc:
                line += f": {col_desc}"

            text += line + "\n"

    return text
