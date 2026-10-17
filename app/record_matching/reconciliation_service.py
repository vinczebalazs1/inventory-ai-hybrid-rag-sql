"""Public opt-in reconciliation API; document extraction and LLM calls are untouched."""
import hashlib
import logging
from time import perf_counter
from typing import Protocol

from app.document_processing.models import ProcessingResult
from app.services.schema_service import load_schema
from .comparison_service import compare_fields
from .config import MatchingSettings
from .matching_engine import MatchingEngine
from .models import (ActionType, CandidateSearchResult, MatchStatus, ProcessingMetadata,
                     ReconciliationResult, Scalar, SearchMetadata, SuggestedAction, ValidationSummary)
from .preparation import prepare_document
from .suggestion_engine import suggest_actions

logger = logging.getLogger(__name__)


class CandidateRepository(Protocol):
    def search(self, values: dict[str, Scalar], expected_columns: dict[str, str],
               settings: MatchingSettings) -> CandidateSearchResult: ...


def reconcile_document(processing_result: ProcessingResult, *, repository: CandidateRepository | None = None,
                       settings: MatchingSettings | None = None,
                       columns: dict[str, str] | None = None) -> ReconciliationResult:
    start = perf_counter()
    metadata = ProcessingMetadata(strategy=settings.strategy if settings else "hybrid")
    output = ReconciliationResult(source_document=processing_result.parsed_document.source_name,
                document_type=processing_result.extraction.document_type, match_status=MatchStatus.ERROR,
                processing_metadata=metadata)
    stage = "configuration"
    try:
        settings = settings or MatchingSettings.from_env()
        metadata.strategy = settings.strategy
        metadata.settings_fingerprint = hashlib.sha256(settings.model_dump_json().encode()).hexdigest()[:16]
        if columns is None:
            columns = {item["column"]: item["type"] for item in load_schema()[settings.target_table]}
        stage = "preparation"
        document = prepare_document(processing_result, columns, settings)
        output.prepared_document = document
        output.warnings = list(document.warnings)
        output.validation_summary = ValidationSummary(
            valid_fields=sum(item.validation_status == "VALID" for item in document.fields),
            invalid_fields=sum(item.validation_status != "VALID" for item in document.fields),
            unmapped_fields=document.unmapped_count,
            missing_evidence_fields=sorted({item.target_field for item in document.fields if not item.evidence}),
            issues=document.validation_issues)
        engine = MatchingEngine(settings)
        empty_search = CandidateSearchResult(metadata=SearchMetadata(candidate_limit=settings.max_candidates))
        preflight = engine.match(document, empty_search, columns)
        if preflight.status in (MatchStatus.CONFLICTING_DATA, MatchStatus.INSUFFICIENT_DATA):
            search, decision = empty_search, preflight
        else:
            stage = "candidate_search"
            if repository is None:
                from .repository import InventoryRepository
                repository = InventoryRepository()
            search_start = perf_counter()
            try:
                search = repository.search(document.values, columns, settings)
            finally:
                metadata.candidate_search_ms = (perf_counter() - search_start) * 1000
            output.search_metadata = search.metadata
            stage = "scoring"
            score_start = perf_counter()
            decision = engine.match(document, search, columns)
            metadata.scoring_ms = (perf_counter() - score_start) * 1000
            metadata.compared_records = len(search.records)
        output.search_metadata = search.metadata
        output.warnings.extend(search.metadata.warnings)
        output.match_status, output.reasons = decision.status, decision.reasons
        output.candidates, output.matched_record = decision.candidates, decision.matched_record
        stage = "comparison"
        if decision.matched_record:
            output.field_comparisons = compare_fields(document, decision.matched_record, columns)
        else:
            # Candidate rank is a display reference, never an invented DB identity.
            for candidate in decision.candidates:
                if "inventory_number" in candidate.matching_fields:
                    output.field_comparisons.extend(compare_fields(document, candidate, columns))
        stage = "suggestions"
        output.suggested_actions = suggest_actions(document, decision, output.field_comparisons,
                                                   search.metadata, columns, settings)
        output.review_required = decision.review_required or any(action.review_required for action in output.suggested_actions)
    except Exception as exc:
        # Driver/configuration exception messages can contain secrets. Never expose them.
        logger.error("Reconciliation failed: stage=%s exception_type=%s", stage, type(exc).__name__)
        output.match_status = MatchStatus.ERROR
        output.matched_record = None
        output.review_required = True
        output.reasons = [f"Az egyeztetés nem fejezhető be ({stage}). Ellenőrizd a konfigurációt és az adatbázis elérhetőségét."]
        output.suggested_actions = [SuggestedAction(action_type=ActionType.MANUAL_REVIEW, reason=output.reasons[0])]
    metadata.reconciliation_ms = (perf_counter() - start) * 1000
    logger.info("Reconciliation completed: status=%s candidates=%d review=%s", output.match_status.value,
                len(output.candidates), output.review_required)
    return output
