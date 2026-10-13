"""Strict, hand-labelled synthetic evaluation inputs, separate from inventory data."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Value = str | int | float | None


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DocumentField(FixtureModel):
    field: str
    value: Value
    raw: str | None = None
    label: str | None = None
    evidence: str | None = None
    invalid: bool = False


class FixtureRecord(FixtureModel):
    record_id: str
    values: dict[str, Value]


class ExpectedDelta(FixtureModel):
    record_id: str
    field: str


class ExpectedOutcome(FixtureModel):
    record_ids: list[str]
    match_status: str
    actions: list[str]
    review_required: bool
    uncertain: bool = False
    identity_evaluable: bool = True
    deltas: list[ExpectedDelta] = Field(default_factory=list)


class EvaluationCase(FixtureModel):
    id: str
    split: Literal["calibration", "test"]
    category: str
    description: str
    document_fields: list[DocumentField]
    records: list[FixtureRecord]
    unique_keys: list[list[str]] = Field(default_factory=lambda: [["item_code"]])
    schema_types: dict[str, str] = Field(default_factory=dict)
    search_status: Literal["complete", "partial", "error", "timeout", "schema_mismatch"] = "complete"
    unmapped_fields: list[dict[str, str]] = Field(default_factory=list)
    expected: ExpectedOutcome

    @model_validator(mode="after")
    def validate_record_references(self):
        record_ids = [record.record_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Fixture-local record identifiers must be unique")
        references = set(self.expected.record_ids) | {delta.record_id for delta in self.expected.deltas}
        if not references.issubset(record_ids):
            raise ValueError("Ground truth refers to a missing fixture record")
        if len(self.expected.record_ids) != len(set(self.expected.record_ids)):
            raise ValueError("Duplicate expected identity")
        return self


class EvaluationDataset(FixtureModel):
    version: Literal[1]
    description: str
    split_policy: str
    cases: list[EvaluationCase]

    @model_validator(mode="after")
    def unique_cases(self):
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Case identifiers must be unique")
        return self


def load_dataset(path: str | Path) -> EvaluationDataset:
    return EvaluationDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))
