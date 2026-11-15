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
from .models import (ActionType, CandidateSearchResult, ComparisonStatus, MatchStatus, OccurrenceCounts, PreparedDocument, ProcessingMetadata,
                     ReconciliationResult, Scalar, SearchMetadata, SuggestedAction, ValidationSummary)
from .preparation import prepare_document
from .suggestion_engine import suggest_actions
from .grouping import group_document

logger = logging.getLogger(__name__)


class CandidateRepository(Protocol):
    def search(self, values: dict[str, Scalar], expected_columns: dict[str, str],
               settings: MatchingSettings) -> CandidateSearchResult: ...


def _reconcile_one(processing_result: ProcessingResult, *, repository: CandidateRepository | None = None,
                       settings: MatchingSettings | None = None,
                       columns: dict[str, str] | None = None, isolated_group: bool = False) -> ReconciliationResult:
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
        document = prepare_document(processing_result, columns, settings, isolated_group=isolated_group)
        output.prepared_document = document
        output.asset_group_id = document.asset_group_id
        output.warnings = list(document.warnings)
        output.validation_summary = ValidationSummary(
            valid_fields=sum(item.validation_status == "VALID" for item in document.fields),
            invalid_fields=sum(item.validation_status in {"INVALID", "UNPARSEABLE", "UNSUPPORTED"} for item in document.fields),
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
        exact_inventory = [row for row in decision.candidates if "inventory_number" in row.matching_fields]
        if len(exact_inventory) == 1:
            row = exact_inventory[0]
            output.critical_conflict_fields = sorted(set(row.identifier_conflicts + (["name"] if row.technical_conflict else [])))
            if row.verified_identifier_match and search.metadata.inventory_lookup.complete:
                output.identified_record = row
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
    output.counts = occurrence_counts(output)
    logger.info("Reconciliation completed: status=%s candidates=%d review=%s", output.match_status.value,
                len(output.candidates), output.review_required)
    return output


def occurrence_counts(result: ReconciliationResult) -> OccurrenceCounts:
    fields = result.prepared_document.fields if result.prepared_document else []
    comparisons = result.field_comparisons
    def occurrences(status):
        return len({(c.occurrence_id, c.field) for c in comparisons if c.status == status})
    return OccurrenceCounts(
        occurrences=len(fields), normalized_occurrences=sum(f.normalized_value is not None for f in fields),
        equal_occurrences=occurrences(ComparisonStatus.EQUAL),
        differing_occurrences=occurrences(ComparisonStatus.DIFFERENT),
        unique_differing_fields=len({c.field for c in comparisons if c.status == ComparisonStatus.DIFFERENT}),
        invalid_occurrences=sum(f.validation_status in {"INVALID", "UNPARSEABLE", "UNSUPPORTED"} for f in fields),
        missing_or_unknown_occurrences=sum(f.validation_status in {"MISSING", "EXPLICIT_EMPTY", "EXPLICIT_UNKNOWN"} for f in fields),
        internal_conflict_fields=len(result.prepared_document.internal_conflicts) if result.prepared_document else 0,
        uncertain_occurrences=len({f.occurrence_id for f in fields if f.extraction_uncertain or not f.evidence}
                                  | {c.occurrence_id for c in comparisons if c.status == ComparisonStatus.UNCERTAIN}))


def reconcile_document(processing_result: ProcessingResult, *, repository: CandidateRepository | None = None,
                       settings: MatchingSettings | None = None,
                       columns: dict[str, str] | None = None) -> ReconciliationResult:
    """Reconcile explicit asset groups independently; never mix field values.

    The legacy single-asset API stays at the root. For multiple assets the root
    is an aggregate with group_results, not a fabricated selected record.
    """
    groups, unassigned, reasons = group_document(processing_result)
    results = [_reconcile_one(group, repository=repository, settings=settings, columns=columns,
                              isolated_group=len(groups) > 1) for group in groups]
    if len(results) == 1:
        result = results[0]
    else:
        result = ReconciliationResult(source_document=processing_result.parsed_document.source_name,
            document_type=processing_result.extraction.document_type, match_status=MatchStatus.MULTIPLE_ASSETS,
            asset_group_count=len(results), group_results=results,
            review_required=any(r.review_required for r in results),
            processing_metadata=ProcessingMetadata(strategy=settings.strategy if settings else "hybrid",
                reconciliation_ms=sum(r.processing_metadata.reconciliation_ms for r in results)),
            field_comparisons=[c for r in results for c in r.field_comparisons],
            suggested_actions=[a for r in results for a in r.suggested_actions],
            search_metadata=SearchMetadata(scope="asset_groups", complete=all(r.search_metadata.complete for r in results),
                truncated=any(r.search_metadata.truncated for r in results),
                timed_out=any(r.search_metadata.timed_out for r in results),
                scanned_rows=sum(r.search_metadata.scanned_rows for r in results)),
            prepared_document=PreparedDocument(possible_multiple_entities=True,
                fields=[f for r in results if r.prepared_document for f in r.prepared_document.fields]),
            reasons=[f"{len(results)} külön eszközcsoport; az értékek és javaslatok csoportonként értendők."],
            counts=OccurrenceCounts(**{name: sum(getattr(r.counts, name) for r in results)
                                       for name in OccurrenceCounts.model_fields}))
    result.unassigned_fields, result.grouping_reasons = unassigned, reasons
    if unassigned:
        result.counts.unassigned_occurrences = len(unassigned)
        result.counts.occurrences += len(unassigned)
        result.counts.normalized_occurrences += sum(f.normalized_value is not None for f in unassigned)
        result.counts.invalid_occurrences += sum(f.normalization_status in {"INVALID", "UNPARSEABLE"} for f in unassigned)
        result.counts.missing_or_unknown_occurrences += sum(f.normalization_status in {"MISSING", "EXPLICIT_UNKNOWN"} for f in unassigned)
        result.counts.uncertain_occurrences += sum(f.extraction_uncertain or not f.evidence for f in unassigned)
        result.review_required = True
        result.suggested_actions = [SuggestedAction(action_type=ActionType.MANUAL_REVIEW,
                                    reason="Nem minden mező rendelhető egyértelműen eszközhöz.")]
        for child in result.group_results:
            child.review_required = True
            child.suggested_actions = [SuggestedAction(action_type=ActionType.MANUAL_REVIEW,
                asset_group_id=child.asset_group_id, reason="A dokumentum nem hozzárendelhető mezőit előbb tisztázni kell.")]
    return result
