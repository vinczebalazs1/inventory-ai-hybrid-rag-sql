"""Schema-independent chunk extraction, evidence checking and lossless merge."""
import json
import logging
from collections.abc import Iterator

from .config import Settings
from .llm_json import prompt, request_json
from .models import ExtractedField, ExtractionResult, Model, ParsedDocument

logger = logging.getLogger(__name__)


class ChunkExtraction(Model):
    document_type: str | None = None
    fields: list[ExtractedField]


def chunks(text: str, size: int, overlap: int) -> Iterator[str]:
    if not 0 <= overlap < size:
        raise ValueError("Require 0 <= overlap < size")
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n\n", start + size // 2, end)
            if boundary >= 0:
                end = boundary + 2
        yield text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def _whitespace(text: str) -> str:
    return " ".join(text.split())


def extract_fields(document: ParsedDocument, settings: Settings) -> ExtractionResult:
    # Page metadata travels separately from text, including continuation chunks.
    sources = document.pages.items() if document.pages else [(None, document.extraction_text)]
    fields: list[ExtractedField] = []
    seen: set[tuple] = set()
    document_types: list[str] = []
    count = 0
    for page, text in sources:
        for chunk in chunks(text, settings.chunk_size, settings.chunk_overlap):
            count += 1
            result = request_json(prompt(
                "document_extraction.txt", schema=json.dumps(ChunkExtraction.model_json_schema()),
                page=json.dumps(page), text=chunk,
            ), ChunkExtraction, settings.model)
            if result.document_type and result.document_type not in document_types:
                document_types.append(result.document_type)
            for field in result.fields:
                evidence = field.evidence
                if not evidence or _whitespace(evidence) not in _whitespace(chunk):
                    evidence = None
                checked = field.model_copy(update={
                    "evidence": evidence,
                    "page": page if evidence is not None else None,
                })
                key = (checked.label, checked.value, checked.evidence)
                if key not in seen:
                    seen.add(key)
                    fields.append(checked)
    logger.info("Extraction completed: chunks=%d fields=%d", count, len(fields))
    return ExtractionResult(
        source_name=document.source_name,
        document_type=" / ".join(document_types) or None, fields=fields,
    )
