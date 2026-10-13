"""Offline runs of the real service with an explicitly simulated repository."""
import csv
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import platform
from importlib.metadata import version
from time import perf_counter

from app.document_processing.models import (ExtractedField, ExtractionResult, MappedField,
    MappingResult, ParsedDocument, ProcessingResult, ValidationIssue)
from app.document_processing.validation_service import normalize
from app.record_matching.candidate_service import select_candidates
from app.record_matching.config import MatchingSettings
from app.record_matching.models import CandidateSearchResult, ComparisonStatus, SchemaInfo, SearchMetadata
from app.record_matching.reconciliation_service import reconcile_document
from app.record_matching.repository import record_from_row
from app.services.schema_service import load_schema
from .dataset import EvaluationCase, load_dataset
from .metrics import Observation, compute_metrics


def case_columns(case: EvaluationCase) -> dict[str, str]:
    columns = {column["column"]: column["type"] for column in load_schema()["inventory_items"]}
    columns.update(case.schema_types)
    return columns


def processing_input(case: EvaluationCase) -> ProcessingResult:
    columns = case_columns(case)
    fields, extracted, issues, lines = [], [], [], []
    for original in case.document_fields:
        raw = original.raw if original.raw is not None else "" if original.value is None else str(original.value)
        label = original.label or original.field
        line = f"{label}: {raw}"
        evidence = original.evidence if "evidence" in original.model_fields_set else line
        lines.append(line)
        value = original.value
        if not original.invalid and value is not None:
            value = normalize(raw, columns[original.field], original.field)
        if original.invalid:
            issues.append(ValidationIssue(field=original.field, severity="warning", message="Kézzel jelölt hibás bemenet."))
        fields.append(MappedField(source_label=label, raw_value=raw, normalized_value=value,
                                  target_field=original.field, evidence=evidence, page=1))
        extracted.append(ExtractedField(label=label, value=raw, evidence=evidence, page=1))
    text = "\n".join(lines)
    return ProcessingResult(parsed_document=ParsedDocument(source_name=case.id + ".pdf", source_extension=".pdf",
                            markdown=text, extraction_text=text, pages={1: text}),
            extraction=ExtractionResult(source_name=case.id + ".pdf", document_type="synthetic_inventory", fields=extracted),
            mapping=MappingResult(mapped_fields=fields, unmapped_fields=[ExtractedField(**field) for field in case.unmapped_fields]),
            validation_issues=issues)


class FixtureRepository:
    """In-memory retrieval includes actual selection/limits but no PostgreSQL latency."""
    def __init__(self, case: EvaluationCase):
        self.case = case
        self.columns = case_columns(case)
        self.schema = SchemaInfo(columns=self.columns, unique_keys=case.unique_keys, verified=True,
                                 compatible=case.search_status != "schema_mismatch")
        self.rows = [record_from_row({name: record.values.get(name) for name in self.columns}, self.schema)
                     for record in case.records]

    def fixture_identity(self, record) -> str | None:
        if record is None:
            return None
        for source, candidate in zip(self.case.records, self.rows):
            if record.values == candidate.values:
                return source.record_id
        return None

    def search(self, values, expected_columns, settings):
        start = perf_counter()
        if self.case.search_status == "error":
            raise ConnectionError("Simulated offline database failure")
        records, truncated = select_candidates(self.rows, values, settings)
        complete = self.case.search_status == "complete" and not truncated
        if self.case.search_status in ("timeout", "schema_mismatch"):
            records = []
        scope = "full_table" if settings.strategy == "hybrid" else "exact_identifiers"
        if not complete:
            scope = "fixture_" + self.case.search_status
        return CandidateSearchResult(records=records, metadata=SearchMetadata(schema_info=self.schema,
            complete=complete, scope=scope, strategies=["offline_" + settings.strategy],
            candidate_limit=settings.max_candidates, returned_candidates=len(records), scanned_rows=len(self.rows),
            truncated=truncated or self.case.search_status == "partial", timed_out=self.case.search_status == "timeout",
            duration_ms=(perf_counter() - start) * 1000))


def evaluate_case(case: EvaluationCase, strategy: str, repeats: int = 3) -> Observation:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    repository = FixtureRepository(case)
    processing = processing_input(case)
    settings = MatchingSettings(strategy=strategy)
    timings = {"candidate_search": [], "scoring": [], "total": []}
    previous = None
    for _ in range(repeats):
        result = reconcile_document(processing, repository=repository, settings=settings, columns=repository.columns)
        stable = result.model_dump(mode="json")
        stable["processing_metadata"] = {key: value for key, value in stable["processing_metadata"].items() if not key.endswith("_ms")}
        stable["search_metadata"].pop("duration_ms")
        if previous is not None and previous != stable:
            raise AssertionError(f"Nondeterministic decision for {case.id}/{strategy}")
        previous = stable
        metadata = result.processing_metadata
        timings["candidate_search"].append(metadata.candidate_search_ms)
        timings["scoring"].append(metadata.scoring_ms)
        timings["total"].append(metadata.reconciliation_ms)
    selected = repository.fixture_identity(result.matched_record)
    expected = case.expected
    return Observation(case_id=case.id, split=case.split, strategy=strategy,
        expected_records=tuple(expected.record_ids), ranked_records=tuple(filter(None, (repository.fixture_identity(row) for row in result.candidates))),
        selected_record=selected, expected_status=expected.match_status, status=result.match_status.value,
        expected_actions=tuple(expected.actions), actions=tuple(action.action_type.value for action in result.suggested_actions),
        expected_review=expected.review_required, review_required=result.review_required,
        uncertain=expected.uncertain, identity_evaluable=expected.identity_evaluable,
        expected_deltas=tuple((delta.record_id, delta.field) for delta in expected.deltas),
        predicted_deltas=tuple(sorted({(selected, field.field) for field in result.field_comparisons
                                      if field.status == ComparisonStatus.DIFFERENT and selected is not None})),
        supplied_records=len(case.records), examined_records=result.search_metadata.scanned_rows,
        supplied_fields=len(case.document_fields), search_complete=result.search_metadata.complete, timings_ms=timings)


def run_evaluation(dataset_path: Path, output_dir: Path, repeats: int = 3) -> dict:
    dataset = load_dataset(dataset_path)
    observations = [evaluate_case(case, strategy, repeats) for strategy in ("exact_only", "hybrid") for case in dataset.cases]
    metrics = {split: {strategy: compute_metrics([o for o in observations if o.split == split and o.strategy == strategy])
                      for strategy in ("exact_only", "hybrid")} for split in ("calibration", "test")}
    report = {"dataset_sha256": sha256(dataset_path.read_bytes()).hexdigest(), "python": platform.python_version(),
              "settings": {strategy: MatchingSettings(strategy=strategy).model_dump() for strategy in ("exact_only", "hybrid")},
              "repeats": repeats, "dataset_cases": len(dataset.cases), "metrics": metrics,
              "measurement_scope": "Offline synthetic retrieval and actual matching service; no LLM or PostgreSQL latency.",
              "reference_policy": "Frozen manual expectations may disagree with implementation; discrepancies are retained in CSV."}
    root = Path(__file__).resolve().parents[2]
    sources = sorted((root / "app/record_matching").glob("*.py")) + sorted((root / "app/evaluation").glob("*.py"))
    report["implementation_sha256"] = sha256(b"".join(path.name.encode() + path.read_bytes() for path in sources)).hexdigest()
    report["libraries"] = {name: version(name) for name in ("rapidfuzz", "pydantic", "psycopg2-binary")}
    report["hybrid_minus_baseline"] = {}
    for split in ("calibration", "test"):
        report["hybrid_minus_baseline"][split] = {}
        for metric in ("precision", "recall", "f1", "top_1_accuracy"):
            baseline, hybrid = (metrics[split][strategy]["matching"][metric] for strategy in ("exact_only", "hybrid"))
            report["hybrid_minus_baseline"][split][metric] = None if baseline is None or hybrid is None else hybrid - baseline
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "matching_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = [asdict(observation) for observation in observations]
    with (output_dir / "matching_cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (tuple, dict, list)) else value
                             for key, value in row.items()})
    return report
