"""Run the existing matcher with fixed source fields; report disagreements honestly."""
from datetime import datetime, timezone
from time import perf_counter

from app.document_processing.models import (ExtractedField, ExtractionResult, MappedField, MappingResult,
                                            ParsedDocument, ProcessingResult)
from app.document_processing.validation_service import validate_fields
from app.evaluation.dataset import EvaluationCase, ExpectedOutcome, FixtureRecord
from app.evaluation.runner import FixtureRepository
from app.record_matching.config import MatchingSettings
from app.record_matching.reconciliation_service import reconcile_document
from app.services.schema_service import load_schema
from .artifacts import dataset_hash, source_hashes
from .documents import document_lines


def processing_input(case, *, parsed=None):
    """Oracle-supplied extraction/mapping, deliberately not labelled as LLM evaluation."""
    text = "\n".join(document_lines(case))
    source = case["document_id"] + ".fixture"
    fields = case["expected_fields"]
    extracted = [ExtractedField(label=f["label"], value=f["raw"], evidence=f"{f['label']}: {f['raw']}") for f in fields]
    mapping = MappingResult(mapped_fields=[MappedField(source_label=f["label"], raw_value=f["raw"],
        target_field=f["field"], evidence=f"{f['label']}: {f['raw']}") for f in fields])
    issues = validate_fields(mapping, load_schema()["inventory_items"])
    return ProcessingResult(parsed_document=parsed or ParsedDocument(source_name=source, source_extension=".fixture",
        markdown=text, extraction_text=text), extraction=ExtractionResult(source_name=source,
        document_type="synthetic_inventory", fields=extracted), mapping=mapping, validation_issues=issues)


def fixture_repository(rows):
    case = EvaluationCase(id="clean_inventory", split="test", category="clean", description="Generated clean inventory",
        document_fields=[], records=[FixtureRecord(record_id=r.inventory_number, values=r.model_dump()) for r in rows],
        unique_keys=[["inventory_number"]], expected=ExpectedOutcome(record_ids=[], match_status="unused", actions=[], review_required=True))
    return FixtureRepository(case)


def assess(case, result) -> dict:
    actual_identity = result.matched_record.values.get("inventory_number") if result.matched_record else None
    actual_deltas = sorted({field.field for field in result.field_comparisons if field.status.value == "DIFFERENT"})
    delta_values = [{"field": field.field, "database_value": field.database_value,
                     "document_value": field.normalized_document_value}
                    for field in result.field_comparisons if field.status.value == "DIFFERENT"]
    actual_actions = sorted(action.action_type.value for action in result.suggested_actions)
    checks = {"match_category": result.match_status.value == case["expected_match_category"],
              "identity": actual_identity == case["expected_inventory_number"],
              "field_differences": sorted(delta_values, key=lambda f: f["field"]) ==
                                   sorted(case["expected_field_differences"], key=lambda f: f["field"]),
              "actions": actual_actions == sorted(case["expected_suggested_actions"]),
              "review": result.review_required == case["expected_review_requirement"]}
    return {"document_id": case["document_id"], "scenario": case["scenario"], "passed": all(checks.values()),
            "checks": checks, "expected_category": case["expected_match_category"], "actual_category": result.match_status.value,
            "expected_inventory_number": case["expected_inventory_number"], "actual_inventory_number": actual_identity,
            "actual_differences": actual_deltas, "actual_delta_values": delta_values,
            "actual_actions": actual_actions, "review_required": result.review_required,
            "search_scope": result.search_metadata.scope, "search_complete": result.search_metadata.complete,
            "search_metadata": result.search_metadata.model_dump(mode="json"),
            "leading_candidates": [{"inventory_number": c.values.get("inventory_number"),
                 "score": c.similarity_score, "identifier_conflicts": c.identifier_conflicts,
                 "technical_conflict": c.technical_conflict} for c in result.candidates[:5]],
            "reasons": result.reasons, "duration_ms": result.processing_metadata.reconciliation_ms}


def evaluate(rows, truth, *, repository=None, mode="offline", settings=None):
    repository = repository or fixture_repository(rows)
    settings = settings or MatchingSettings()
    started = perf_counter()
    cases = [assess(case, reconcile_document(processing_input(case), repository=repository, settings=settings))
             for case in truth["scenarios"]]
    source_hash, source_manifest = source_hashes()
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
            "pipeline_scope": "Known structured fields -> real validation, preparation, repository search, matching, deltas and suggestions; no LLM.",
            "canonical_dataset_sha256": dataset_hash(rows), "implementation_sha256": source_hash,
            "source_manifest": source_manifest, "settings": settings.model_dump(),
            "passed": sum(c["passed"] for c in cases), "failed": sum(not c["passed"] for c in cases),
            "cases": cases, "duration_ms": (perf_counter() - started) * 1000}
