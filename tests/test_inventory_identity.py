"""Acceptance cases for inventory-number-first identification (T01–T22)."""
import json

import pytest

from app.evaluation.dataset import DocumentField, EvaluationCase, ExpectedOutcome, FixtureRecord
from app.evaluation.runner import FixtureRepository, case_columns, processing_input
from app.record_matching.config import MatchingSettings
from app.record_matching.models import ActionType as A, MatchStatus as S, ReconciliationResult
from app.record_matching.reconciliation_service import reconcile_document
from app.record_matching.repository import record_from_row


def reconcile(document, records, *, unique=None, settings=None, search="complete"):
    case = EvaluationCase(id="inventory_unit", split="test", category="inventory", description="Independent acceptance case",
        document_fields=[DocumentField(field=k, value=v) for k, v in document.items()] if isinstance(document, dict) else document,
        records=[FixtureRecord(record_id=str(i), values=row) for i, row in enumerate(records)],
        unique_keys=[["inventory_number"]] if unique is None else unique, search_status=search,
        expected=ExpectedOutcome(record_ids=[], match_status="unused", actions=[], review_required=True))
    return reconcile_document(processing_input(case), repository=FixtureRepository(case), columns=case_columns(case),
                              settings=settings or MatchingSettings())


def action_types(result):
    return {action.action_type for action in result.suggested_actions}


def test_T01_T02_primary_key_is_existing_inventory_number_and_no_unnecessary_update():
    row = {"inventory_number": "L-94279", "item_code": "E0001", "sub_code": 0, "name": "Printer", "location": "KGK"}
    result = reconcile(row, [row], unique=[["item_code"], ["inventory_number"]])
    assert result.match_status == S.EXACT_MATCH
    assert result.matched_record.record_id == '{"inventory_number":"L-94279"}'
    assert result.matched_record.strategy == "inventory_number_exact"
    assert result.matched_record.similarity_score == 1.0
    assert result.search_metadata.identity_verified
    assert action_types(result) == {A.ATTACH_DOCUMENT}


def test_T03_location_difference_does_not_change_identity_and_preserves_evidence():
    result = reconcile({"inventory_number": "L-94279", "location": "KGK"},
                       [{"inventory_number": "L-94279", "location": "LIB"}])
    assert result.match_status == S.EXACT_MATCH
    delta = next(c for c in result.field_comparisons if c.field == "location")
    assert (delta.database_value, delta.normalized_document_value, delta.evidence) == ("LIB", "KGK", "location: KGK")
    update = next(a for a in result.suggested_actions if a.action_type == A.UPDATE_CANDIDATE)
    assert update.target_identity_verified and update.affected_fields == ["location"]
    assert all(not a.executable for a in result.suggested_actions)


@pytest.mark.parametrize("limit", [1, 5, 100])
def test_T04_T05_primary_lookup_does_not_scan_thousands_of_shared_item_codes(limit):
    rows = [{"inventory_number": f"L-{i:05}", "item_code": "PRINTER", "sub_code": 0, "name": "Printer"} for i in range(4000)]
    result = reconcile(rows[1234], rows, settings=MatchingSettings(max_candidates=limit, max_scan_rows=limit))
    assert result.match_status == S.EXACT_MATCH
    metadata = result.search_metadata
    assert metadata.complete and not metadata.truncated
    assert metadata.inventory_lookup.complete and metadata.inventory_lookup.matching_rows == 1
    assert metadata.inventory_lookup.unique_constraint_verified
    assert not metadata.fuzzy_search.attempted and not metadata.secondary_lookup.attempted
    assert metadata.scanned_rows == 1 and not metadata.absence_check_complete
    assert metadata.scope == "verified_identifier"


def test_T06_no_unique_guarantee_still_shows_reviewable_differences():
    result = reconcile({"inventory_number": "L-1", "location": "KGK"},
                       [{"inventory_number": "L-1", "location": "LIB"}], unique=[])
    assert result.match_status == S.LIKELY_MATCH
    assert result.matched_record.record_id is None
    assert result.matched_record.strategy == "inventory_number_unverified"
    assert not result.search_metadata.identity_verified
    assert action_types(result) == {A.UPDATE_CANDIDATE, A.MANUAL_REVIEW}
    update = result.suggested_actions[0]
    assert update.target_record is None and update.candidate_rank == 1
    assert not update.target_identity_verified and not update.executable


@pytest.mark.parametrize("limit", [1, 10])
def test_T07_duplicates_are_not_disambiguated_by_a_secondary_key(limit):
    rows = [{"inventory_number": "DUP", "item_code": "A", "location": "LIB"},
            {"inventory_number": "DUP", "item_code": "B", "location": "KGK"}]
    result = reconcile({"inventory_number": "DUP", "item_code": "A"}, rows,
                       unique=[["item_code"]], settings=MatchingSettings(max_candidates=limit))
    assert result.match_status == S.AMBIGUOUS_MATCH and result.matched_record is None
    assert A.ATTACH_DOCUMENT not in action_types(result)
    assert result.search_metadata.inventory_lookup.matching_rows == 2


def test_T08_null_inventory_has_no_inventory_identity():
    result = reconcile({"item_code": "A"}, [{"item_code": "A", "inventory_number": None}], unique=[["item_code"], ["inventory_number"]])
    assert not result.search_metadata.inventory_lookup.attempted
    assert result.matched_record.identity_fields == ["item_code"]


@pytest.mark.parametrize("other", ["L-001", "l-0001", "L0001", " L-0001 "])
def test_T09_stored_identifier_characters_and_leading_zeroes_are_not_collapsed(other):
    result = reconcile({"inventory_number": "L-0001"}, [{"inventory_number": other}])
    assert result.match_status == S.NO_MATCH
    assert result.search_metadata.inventory_lookup.matching_rows == 0
    assert A.ATTACH_DOCUMENT not in action_types(result)


def test_T10_conflicting_identifiers_keep_both_candidates_and_block_exact():
    result = reconcile({"inventory_number": "L-1", "item_code": "B"},
                       [{"inventory_number": "L-1", "item_code": "A"}, {"inventory_number": "L-2", "item_code": "B"}])
    assert result.match_status == S.CONFLICTING_DATA
    assert len(result.candidates) == 2 and not result.search_metadata.identity_verified
    assert result.search_metadata.secondary_lookup.attempted


def test_T11_verified_secondary_composite_finishes_with_one_candidate():
    result = reconcile({"item_code": "A", "sub_code": 2}, [{"item_code": "A", "sub_code": i} for i in range(100)],
                       unique=[["item_code", "sub_code"]], settings=MatchingSettings(max_candidates=1, max_scan_rows=1))
    assert result.match_status == S.EXACT_MATCH
    assert result.matched_record.record_id == '{"item_code":"A","sub_code":2}'
    assert result.search_metadata.secondary_lookup.unique_constraint_verified
    assert not result.search_metadata.fuzzy_search.attempted


def test_T12_fuzzy_name_and_location_are_not_unique_identity():
    result = reconcile({"name": "Dell Latitdue 5540", "location": "KGK"},
                       [{"inventory_number": "L-1", "name": "Dell Latitude 5540", "location": "KGK"}])
    assert result.match_status == S.LIKELY_MATCH
    assert result.search_metadata.fuzzy_search.complete and result.review_required


def test_T13_missing_primary_falls_back_and_checks_similar_records():
    result = reconcile({"inventory_number": "NEW", "name": "Dell Latitude 5540"},
                       [{"inventory_number": "OLD", "name": "Dell Latitude 5540"}])
    assert result.search_metadata.inventory_lookup.matching_rows == 0
    assert result.search_metadata.fuzzy_search.attempted and result.candidates
    assert A.CREATE_RECORD_CANDIDATE not in action_types(result)


def test_T14_partial_fuzzy_cannot_prove_absence_but_preserves_primary_candidate():
    rows = [{"inventory_number": "L-1", "name": "Printer", "location": "LIB"}] + [
        {"inventory_number": f"X-{i}", "name": "Printer", "location": "LIB"} for i in range(10)]
    result = reconcile({"inventory_number": "L-1", "name": "Printer", "location": "KGK"}, rows,
                       unique=[], settings=MatchingSettings(max_candidates=1, max_scan_rows=1))
    assert result.match_status == S.SEARCH_INCOMPLETE and result.candidates[0].values["inventory_number"] == "L-1"
    assert result.search_metadata.inventory_lookup.complete and not result.search_metadata.fuzzy_search.complete
    assert not result.search_metadata.absence_check_complete
    assert A.CREATE_RECORD_CANDIDATE not in action_types(result)
    assert A.UPDATE_CANDIDATE in action_types(result)


def test_T15_database_error_is_not_record_absence():
    result = reconcile({"inventory_number": "L-1"}, [], search="error")
    assert result.match_status == S.ERROR and action_types(result) == {A.MANUAL_REVIEW}


@pytest.mark.parametrize("label,invalid", [("inventory_number", True), ("Service Tag", False)])
def test_T16_T17_invalid_or_serial_identifier_cannot_hide_behind_secondary_exact(label, invalid):
    result = reconcile([DocumentField(field="inventory_number", value="L-1", label=label, invalid=invalid),
                        DocumentField(field="item_code", value="A")],
                       [{"inventory_number": "L-1", "item_code": "A"}], unique=[["item_code"], ["inventory_number"]])
    assert result.match_status == S.CONFLICTING_DATA
    assert result.search_metadata.scope == "not_searched"


def test_T22_legacy_output_deserializes_with_optional_new_metadata():
    result = reconcile({"inventory_number": "L-1"}, [{"inventory_number": "L-1"}])
    payload = json.loads(result.model_dump_json())
    for name in ("inventory_lookup", "secondary_lookup", "fuzzy_search", "identity_verified", "absence_check_complete"):
        payload["search_metadata"].pop(name)
    for action in payload["suggested_actions"]:
        action.pop("candidate_rank")
        action.pop("target_identity_verified")
    for comparison in payload["field_comparisons"]:
        comparison.pop("candidate_rank")
    parsed = ReconciliationResult.model_validate_json(json.dumps(payload))
    assert parsed.match_status == S.EXACT_MATCH
    assert not parsed.search_metadata.inventory_lookup.attempted


def test_blank_nullable_unique_value_is_not_a_stable_record_key():
    from app.record_matching.models import SchemaInfo
    schema = SchemaInfo(verified=True, compatible=True, unique_keys=[["inventory_number"]])
    for value in (None, "", "  ", "\t\n"):
        assert record_from_row({"inventory_number": value}, schema).record_id is None


def test_secondary_candidates_survive_incomplete_fuzzy_scan_without_inventory_number():
    rows = [{"item_code": "A", "name": "Office Printer"}] + [
        {"item_code": f"B-{i}", "name": "Office Printer"} for i in range(10)]
    result = reconcile({"item_code": "A", "name": "Office Printer"}, rows,
                       unique=[], settings=MatchingSettings(max_candidates=1, max_scan_rows=1))
    assert result.match_status == S.SEARCH_INCOMPLETE
    assert result.candidates[0].values["item_code"] == "A"


def test_overlapping_searches_preserve_database_duplicates_without_creating_new_ones():
    from app.record_matching.models import DatabaseRecord
    from app.record_matching.repository import _merge_observations
    row = DatabaseRecord(values={"item_code": "A"})
    other = DatabaseRecord(values={"item_code": "B"})
    assert _merge_observations([row, row], [row, row, other]) == [row, row, other]


@pytest.mark.parametrize("with_item_code", [False, True])
def test_sub_code_conflict_vetoes_primary_identity_with_or_without_item_code(with_item_code):
    document = {"inventory_number": "L-1", "sub_code": 2}
    if with_item_code:
        document["item_code"] = "A"
    result = reconcile(document, [{"inventory_number": "L-1", "item_code": "A", "sub_code": 1}])
    assert result.match_status == S.CONFLICTING_DATA
    assert "sub_code" in result.candidates[0].identifier_conflicts
    assert not result.search_metadata.identity_verified and A.ATTACH_DOCUMENT not in action_types(result)
