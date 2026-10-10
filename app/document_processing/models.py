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


class ExtractedField(Model):
    label: str = Field(min_length=1)
    value: str
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


class MappedField(Model):
    source_label: str
    raw_value: str
    target_field: str
    normalized_value: str | int | float | None = None
    page: int | None = None
    evidence: str | None = None


class MappingResult(Model):
    mapped_fields: list[MappedField] = Field(default_factory=list)
    unmapped_fields: list[ExtractedField] = Field(default_factory=list)


class ValidationIssue(Model):
    field: str
    severity: Literal["warning", "error"]
    message: str


class ProcessingResult(Model):
    parsed_document: ParsedDocument
    extraction: ExtractionResult
    mapping: MappingResult
    validation_issues: list[ValidationIssue]
