"""Batch semantic mapping against the live file-based schema."""
import json
import logging

from pydantic import Field

from .config import Settings
from .llm_json import prompt, request_json
from .field_labels import canonical_label
from .models import ExtractionResult, MappedField, MappingResult, Model, Occurrence

logger = logging.getLogger(__name__)


class Assignment(Model):
    index: int = Field(ge=0)
    target_field: str | None


class Assignments(Model):
    assignments: list[Assignment]


def map_fields(extraction: ExtractionResult, columns: list[dict], descriptions: dict,
               settings: Settings) -> MappingResult:
    targets = {col["column"]: {"type": col["type"], "description": descriptions.get(col["column"], "")}
               for col in columns}
    result = MappingResult()
    # A calculation operand is not a recorded inventory value. Retain it for
    # inspection, but never turn a subtraction operator into a negative amount.
    recorded = []
    for field in extraction.fields:
        if field.value_origin == "calculation":
            result.unmapped_fields.append(field)
        else:
            recorded.append(field)
    for start in range(0, len(recorded), settings.mapping_batch_size):
        batch = recorded[start:start + settings.mapping_batch_size]
        response = request_json(prompt(
            "document_mapping.txt", schema=json.dumps(Assignments.model_json_schema()),
            targets=json.dumps(targets, ensure_ascii=False),
            fields=json.dumps([{"index": i, "label": f.label, "value": f.value,
                                "evidence": f.evidence, "page": f.page}
                               for i, f in enumerate(batch)], ensure_ascii=False),
        ), Assignments, settings.model)
        indexes = [assignment.index for assignment in response.assignments]
        if sorted(indexes) != list(range(len(batch))):
            raise ValueError("Mapping must return each input index exactly once")
        by_index = {a.index: a.target_field for a in response.assignments}
        for index, field in enumerate(batch):
            explicit = canonical_label(field.label)
            target = explicit if explicit in targets else by_index[index]
            if target is not None and target not in targets:
                raise ValueError("Mapping returned a target outside the schema")
            if target is None:
                result.unmapped_fields.append(field)
            else:
                result.mapped_fields.append(MappedField(
                    source_label=field.label, raw_value=field.value, target_field=target,
                    page=field.page, evidence=field.evidence,
                    **{name: getattr(field, name) for name in Occurrence.model_fields},
                ))
    logger.info("Mapping completed: mapped=%d unmapped=%d", len(result.mapped_fields), len(result.unmapped_fields))
    return result
