"""Serializable contracts, independent of the inventory schema."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ParsedDocument(Model):
    source_name: str
    source_extension: str
    markdown: str
    extraction_text: str
    pages: dict[int, str] = Field(default_factory=dict)
    raw_document: dict[str, Any] | None = None
    ocr_pages: list[int] = Field(default_factory=list)
    source_cells: dict[int, list[dict[str, Any]]] = Field(default_factory=dict)


class Occurrence(Model):
    """Observed provenance; coordinates/confidence are never estimated by the LLM."""
    occurrence_id: str | None = None
    asset_group_id: str | None = None
    value_origin: Literal["recorded", "calculation"] = "recorded"
    context: str | None = None
    source_span: tuple[int, int] | None = None
    block_id: str | None = None
    table_id: str | None = None
    table_row: int | None = None
    table_column: int | None = None
    bounding_boxes: list[dict[str, Any]] = Field(default_factory=list)
    extraction_method: Literal["text", "ocr", "unknown"] = "unknown"
    extraction_uncertain: bool = False
    uncertainty_reason: str | None = None
    recognition_confidence: float | None = None


class ExtractedField(Occurrence):
    label: str = Field(min_length=1)
    value: str
    value_origin: Literal["recorded", "calculation"] = "recorded"
    page: int | None = Field(default=None, ge=1)
    evidence: str | None = None

    @field_validator("label")
    @classmethod
    def nonblank_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field label must not be blank")
        return value


class ExtractionResult(Model):
    source_name: str
    document_type: str | None = None
    fields: list[ExtractedField]


class MappedField(Occurrence):
    source_label: str
    raw_value: str
    target_field: str
    normalized_value: str | int | float | None = None
    page: int | None = None
    evidence: str | None = None
    normalization_status: Literal["VALID", "MISSING", "EXPLICIT_UNKNOWN", "INVALID", "UNPARSEABLE"] | None = None


class MappingResult(Model):
    mapped_fields: list[MappedField] = Field(default_factory=list)
    unmapped_fields: list[ExtractedField] = Field(default_factory=list)


class ValidationIssue(Model):
    field: str
    severity: Literal["warning", "error"]
    message: str
    occurrence_id: str | None = None
    raw_value: str | None = None
    page: int | None = None
    category: str = "normalization"
    asset_group_id: str | None = None


class ProcessingResult(Model):
    parsed_document: ParsedDocument
    extraction: ExtractionResult
    mapping: MappingResult
    validation_issues: list[ValidationIssue]
