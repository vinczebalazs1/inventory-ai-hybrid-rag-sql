"""Metric definitions are checked against manually computed small examples."""
from dataclasses import replace

import pytest

from app.evaluation.metrics import Observation, compute_metrics


def observation(**changes):
    base = Observation(
        case_id="sample", split="test", strategy="hybrid", expected_records=("right",),
        ranked_records=("right",), selected_record="right", expected_status="EXACT_MATCH",
        status="EXACT_MATCH", expected_actions=("ATTACH_DOCUMENT",), actions=("ATTACH_DOCUMENT",),
        expected_review=False, review_required=False,
    )
    return replace(base, **changes)


def test_wrong_identity_counts_as_both_false_positive_and_false_negative():
    result = compute_metrics([observation(selected_record="wrong", ranked_records=("wrong",))])
    assert result["matching"]["true_positive"] == 0
    assert result["matching"]["false_positive"] == 1
    assert result["matching"]["false_negative"] == 1
    assert result["matching"]["f1"] == 0
    assert result["decisions"]["false_automatic_matches"] == 1


def test_abstention_is_false_negative_but_not_false_positive():
    result = compute_metrics([observation(selected_record=None, ranked_records=(), review_required=True)])
    assert result["matching"]["false_negative"] == 1
    assert result["matching"]["false_positive"] == 0
    assert result["matching"]["precision"] is None
    assert result["matching"]["recall"] == 0
    assert result["decisions"]["review_rate"] == 1
    assert result["decisions"]["abstention_rate"] == 1


def test_rankings_use_fixed_k_and_only_known_existing_records():
    rows = [observation(ranked_records=("wrong", "right")), observation(expected_records=(), selected_record=None)]
    result = compute_metrics(rows)
    assert result["matching"]["ranking_evaluable_cases"] == 1
    assert result["matching"]["top_1_accuracy"] == 0
    assert result["matching"]["at_k"]["3"]["precision_at_k"] == pytest.approx(1 / 3)
    assert result["matching"]["at_k"]["3"]["recall_at_k"] == 1


def test_short_correct_result_is_not_artificial_perfect_precision_at_five():
    result = compute_metrics([observation()])
    assert result["matching"]["at_k"]["5"]["precision_at_k"] == 0.2
    assert result["matching"]["at_k"]["5"]["recall_at_k"] == 1


def test_false_creation_includes_existing_identity_and_unsafe_new_case():
    rows = [
        observation(actions=("CREATE_RECORD_CANDIDATE",)),
        observation(expected_records=(), selected_record=None, actions=("CREATE_RECORD_CANDIDATE",)),
        observation(expected_records=(), selected_record=None, expected_actions=("CREATE_RECORD_CANDIDATE",),
                    actions=("CREATE_RECORD_CANDIDATE",)),
    ]
    assert compute_metrics(rows)["decisions"]["false_create_proposals"] == 2


def test_delta_identity_matters_and_duplicates_are_not_double_counted():
    result = compute_metrics([observation(
        expected_deltas=(("right", "location"), ("right", "quantity")),
        predicted_deltas=(("wrong", "location"), ("right", "quantity"), ("right", "quantity")),
    )])
    assert result["deltas"] == {
        "true_positive": 1, "false_positive": 1, "false_negative": 1,
        "precision": 0.5, "recall": 0.5, "f1": 0.5,
    }


def test_multiple_ground_truth_records_have_correct_recall_denominator():
    result = compute_metrics([observation(expected_records=("right", "second"))])
    assert result["matching"]["recall"] == 0.5
    assert result["matching"]["at_k"]["1"]["recall_at_k"] == 0.5


def test_review_and_abstention_are_distinct():
    result = compute_metrics([observation(review_required=True, uncertain=True)])
    assert result["decisions"]["review_rate"] == 1
    assert result["decisions"]["abstention_rate"] == 0
    assert result["decisions"]["uncertainty_detection_rate"] == 1


def test_empty_metrics_are_undefined_and_p95_requires_twenty_samples():
    assert compute_metrics([])["matching"]["f1"] is None
    result = compute_metrics([observation(timings_ms={"total": [1.0, 2.0, 9.0]})])
    assert result["timings"]["total"] == {"samples": 3, "mean_ms": 4.0, "median_ms": 2.0, "p95_ms": None}
    result = compute_metrics([observation(timings_ms={"total": [float(i) for i in range(1, 21)]})])
    assert result["timings"]["total"]["p95_ms"] == 19


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError):
        compute_metrics([], (0,))
    with pytest.raises(ValueError):
        compute_metrics([], (1, 1))
