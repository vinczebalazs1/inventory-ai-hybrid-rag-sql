"""Validated JSON through the existing LLM wrapper, with one repair."""
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.services import llm_service

T = TypeVar("T", bound=BaseModel)
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def prompt(name: str, **values: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8").format(**values)


def request_json(text: str, response_type: type[T], model: str) -> T:
    raw = llm_service.ask_llm(text, model=model)
    try:
        return response_type.model_validate_json(raw)
    except ValidationError as exc:
        # Do not include input values in error descriptions or production logs.
        errors = json.dumps(exc.errors(include_input=False, include_url=False))
        repair = prompt(
            "document_repair.txt", response=raw, errors=errors,
            schema=json.dumps(response_type.model_json_schema()),
        )
        return response_type.model_validate_json(llm_service.ask_llm(repair, model=model))
