"""No live services: candidate selection and conservative identifier semantics."""
from app.record_matching.candidate_service import escape_like, fuzzy_tokens, select_candidates
from app.record_matching.config import MatchingSettings
from app.record_matching.models import DatabaseRecord


def records(*values):
    return [DatabaseRecord(values=value) for value in values]


def test_identifier_case_and_leading_zeroes_are_not_collapsed():
    result, cut = select_candidates(records({"inventory_number": "INV-001"},
                                           {"inventory_number": "INV-1"},
                                           {"inventory_number": "inv-001"}),
                                    {"inventory_number": "INV-001"}, MatchingSettings())
    assert [record.values["inventory_number"] for record in result] == ["INV-001"]
    assert not cut


def test_duplicate_database_rows_are_preserved_for_ambiguity():
    result, cut = select_candidates(records({"inventory_number": "INV-1"},
                                           {"inventory_number": "INV-1"}),
                                    {"inventory_number": "INV-1"}, MatchingSettings())
    assert len(result) == 2
    assert not cut


def test_fuzzy_retrieval_keeps_different_model_numbers_for_matcher_review():
    result, _ = select_candidates(records({"name": "Dell Latitude 5540"},
                                         {"name": "Dell Latitude 5550"},
                                         {"name": "Vacuum pump"}),
                                  {"name": "Dell Latitdue 5540"}, MatchingSettings())
    assert len(result) == 2


def test_exact_matches_take_priority_and_pruning_is_explicit():
    settings = MatchingSettings(max_candidates=1)
    result, cut = select_candidates(records({"name": "Dell Latitude", "inventory_number": "other"},
                                           {"name": "Dell", "inventory_number": "INV-1"}),
                                    {"name": "Dell Latitude", "inventory_number": "INV-1"}, settings)
    assert cut
    assert result[0].values["inventory_number"] == "INV-1"


def test_exact_only_does_not_return_name_only_candidates():
    result, _ = select_candidates(records({"name": "Dell"}), {"name": "Dell"},
                                  MatchingSettings(strategy="exact_only"))
    assert result == []


def test_ties_are_stable_and_token_prefilter_is_bounded():
    data = records({"name": "Printer", "location": "Z"}, {"name": "Printer", "location": "A"})
    left, _ = select_candidates(data, {"name": "Printer"}, MatchingSettings())
    right, _ = select_candidates(list(reversed(data)), {"name": "Printer"}, MatchingSettings())
    assert left == right
    assert len(fuzzy_tokens("aa bb cc dd ee ff gg hh ii jj kk")) == 8
    assert escape_like("a_%\\b") == "a\\_\\%\\\\b"
