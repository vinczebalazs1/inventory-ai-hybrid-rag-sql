"""Strict JSON contracts. Record identity always comes from verified DB keys."""
from enum import Enum
from typing import Literal

from pydantic import ConfigDict, Field

from app.document_processing.models import Model, ValidationIssue

Scalar = str | int | float | bool | None


class Contract(Model):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class MatchStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    LIKELY_MATCH = "LIKELY_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    NO_MATCH = "NO_MATCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    CONFLICTING_DATA = "CONFLICTING_DATA"
    SEARCH_INCOMPLETE = "SEARCH_INCOMPLETE"
    ERROR = "ERROR"


class ComparisonStatus(str, Enum):
    EQUAL = "EQUAL"
    DIFFERENT = "DIFFERENT"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ActionType(str, Enum):
    ATTACH_DOCUMENT = "ATTACH_DOCUMENT"
    UPDATE_CANDIDATE = "UPDATE_CANDIDATE"
    CREATE_RECORD_CANDIDATE = "CREATE_RECORD_CANDIDATE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class PreparedField(Contract):
    source_label: str
    raw_value: str
    target_field: str
    normalized_value: Scalar = None
    comparison_value: Scalar = None
    evidence: str | None = None
    page: int | None = None
    validation_status: Literal["VALID", "INVALID", "EXPLICIT_EMPTY", "UNSUPPORTED", "CONFLICT"]
    explanation: str = ""


class PreparedDocument(Contract):
    fields: list[PreparedField] = Field(default_factory=list)
    values: dict[str, Scalar] = Field(default_factory=dict)
    blocked: bool = False
    possible_multiple_entities: bool = False
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    unmapped_count: int = 0


class SchemaInfo(Contract):
    table_schema: str = "public"
    table_name: str = "inventory_items"
    columns: dict[str, str] = Field(default_factory=dict)
    primary_key: list[str] = Field(default_factory=list)
    unique_keys: list[list[str]] = Field(default_factory=list)
    verified: bool = False
    compatible: bool = False
    differences: list[str] = Field(default_factory=list)


class DatabaseRecord(Contract):
    record_id: str | None = None
    identity_fields: list[str] = Field(default_factory=list)
    values: dict[str, Scalar]


class SearchStage(Contract):
    """matching_rows is a lower bound when truncated; unattempted is not complete."""
    attempted: bool = False
    complete: bool = False
    matching_rows: int = 0
    truncated: bool = False
    unique_constraint_verified: bool = False
    skipped_reason: str | None = None
    duration_ms: float = 0.0


class SearchMetadata(Contract):
    schema_info: SchemaInfo | None = None
    complete: bool = False
    scope: str = "not_searched"
    strategies: list[str] = Field(default_factory=list)
    candidate_limit: int = 0
    returned_candidates: int = 0
    scanned_rows: int = 0
    truncated: bool = False
    timed_out: bool = False
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    inventory_lookup: SearchStage = Field(default_factory=SearchStage)
    secondary_lookup: SearchStage = Field(default_factory=SearchStage)
    fuzzy_search: SearchStage = Field(default_factory=SearchStage)
    identity_verified: bool = False
    absence_check_complete: bool = False


class CandidateSearchResult(Contract):
    records: list[DatabaseRecord] = Field(default_factory=list)
    metadata: SearchMetadata


class ScoreContribution(Contract):
    field: str
    similarity: float = Field(ge=0, le=1)
    weight: float = Field(ge=0)
    contribution: float = Field(ge=0)
    explanation: str


class CandidateRecord(DatabaseRecord):
    rank: int = Field(ge=1)
    similarity_score: float = Field(ge=0, le=1)
    strategy: str
    matching_fields: list[str] = Field(default_factory=list)
    score_breakdown: list[ScoreContribution] = Field(default_factory=list)
    identifier_conflicts: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_required: bool = True
    verified_identifier_match: bool = False
    technical_conflict: bool = False


class MatchDecision(Contract):
    status: MatchStatus
    candidates: list[CandidateRecord] = Field(default_factory=list)
    matched_record: CandidateRecord | None = None
    reasons: list[str] = Field(default_factory=list)
    review_required: bool = True


class FieldComparison(Contract):
    field: str
    source_label: str | None = None
    raw_document_value: str | None = None
    normalized_document_value: Scalar = None
    database_value: Scalar = None
    normalized_database_value: Scalar = None
    status: ComparisonStatus
    evidence: str | None = None
    page: int | None = None
    explanation: str
    record_id: str | None = None
    candidate_rank: int | None = None


class SuggestedAction(Contract):
    action_type: ActionType
    target_record: str | None = None
    reason: str
    review_required: bool = True
    affected_fields: list[str] = Field(default_factory=list)
    available_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    executable: Literal[False] = False
    candidate_rank: int | None = None
    target_identity_verified: bool = False


class ValidationSummary(Contract):
    valid_fields: int = 0
    invalid_fields: int = 0
    unmapped_fields: int = 0
    missing_evidence_fields: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class ProcessingMetadata(Contract):
    strategy: str
    algorithm_version: str = "1.1"
    settings_fingerprint: str = ""
    reconciliation_ms: float = 0.0
    candidate_search_ms: float = 0.0
    scoring_ms: float = 0.0
    compared_records: int = 0


class ReconciliationResult(Contract):
    source_document: str
    document_type: str | None = None
    match_status: MatchStatus
    review_required: bool = True
    matched_record: CandidateRecord | None = None
    candidates: list[CandidateRecord] = Field(default_factory=list)
    field_comparisons: list[FieldComparison] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    search_metadata: SearchMetadata = Field(default_factory=SearchMetadata)
    processing_metadata: ProcessingMetadata
    prepared_document: PreparedDocument | None = None
