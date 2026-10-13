"""Identity-aware metrics, independent of matching implementation details.

No undefined metric is silently reported as perfect or zero: it is JSON null.
A wrong association is both a false positive and a missed true association.
"""
from collections import Counter
from dataclasses import dataclass, field
from math import ceil
from statistics import mean, median
from typing import Any


@dataclass(frozen=True)
class Observation:
    case_id: str
    split: str
    strategy: str
    expected_records: tuple[str, ...]
    ranked_records: tuple[str, ...]
    selected_record: str | None
    expected_status: str
    status: str
    expected_actions: tuple[str, ...]
    actions: tuple[str, ...]
    expected_review: bool
    review_required: bool
    uncertain: bool = False
    identity_evaluable: bool = True
    expected_deltas: tuple[tuple[str, str], ...] = ()
    predicted_deltas: tuple[tuple[str, str], ...] = ()
    supplied_records: int = 0
    examined_records: int = 0
    supplied_fields: int = 0
    search_complete: bool = False
    timings_ms: dict[str, list[float]] = field(default_factory=dict)


def _divide(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _prf(tp: int, fp: int, fn: int) -> dict[str, int | float | None]:
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": _divide(tp, tp + fp),
        "recall": _divide(tp, tp + fn),
        "f1": _divide(2 * tp, 2 * tp + fp + fn),
    }


def _timing_summary(values: list[float]) -> dict[str, int | float | None]:
    ordered = sorted(values)
    return {
        "samples": len(values),
        "mean_ms": mean(values) if values else None,
        "median_ms": median(values) if values else None,
        # Nearest-rank P95; fewer than 20 samples cannot resolve a 5% tail.
        "p95_ms": ordered[ceil(0.95 * len(ordered)) - 1] if len(ordered) >= 20 else None,
    }


def compute_metrics(observations: list[Observation], ks: tuple[int, ...] = (1, 3, 5)) -> dict[str, Any]:
    """Macro ranking metrics; micro identity/delta precision, recall and F1.

    P@K uses the fixed K denominator, even for shorter returned lists.
    Ranking is evaluated on cases with a known existing identity only.
    Matching precision/recall includes negative cases but excludes explicitly
    non-single-entity examples. Review does not itself erase a proposed link;
    auto-acceptance errors are measured separately.
    """
    if not ks or any(k <= 0 for k in ks) or len(set(ks)) != len(ks):
        raise ValueError("K values must be distinct positive integers")
    identities = [(o, set(o.expected_records)) for o in observations if o.identity_evaluable]
    ranking = [(o, truth) for o, truth in identities if truth]
    tp = fp = fn = 0
    for observation, truth in identities:
        predicted = {observation.selected_record} if observation.selected_record is not None else set()
        tp += len(predicted & truth)
        fp += len(predicted - truth)
        fn += len(truth - predicted)

    delta_tp = delta_fp = delta_fn = 0
    for observation in observations:
        truth = set(observation.expected_deltas)
        predicted = set(observation.predicted_deltas)
        delta_tp += len(truth & predicted)
        delta_fp += len(predicted - truth)
        delta_fn += len(truth - predicted)

    uncertain = [o for o in observations if o.uncertain]
    confusion = Counter((o.expected_status, o.status) for o in observations)
    ranking_metrics = {}
    for k in ks:
        precision = [len(set(o.ranked_records[:k]) & truth) / k for o, truth in ranking]
        recall = [len(set(o.ranked_records[:k]) & truth) / len(truth) for o, truth in ranking]
        ranking_metrics[str(k)] = {
            "precision_at_k": mean(precision) if precision else None,
            "recall_at_k": mean(recall) if recall else None,
        }
    stages = sorted({stage for o in observations for stage in o.timings_ms})
    return {
        "cases": len(observations),
        "matching": {
            **_prf(tp, fp, fn),
            "identity_evaluable_cases": len(identities),
            "ranking_evaluable_cases": len(ranking),
            "top_1_accuracy": _divide(
                sum(bool(o.ranked_records) and o.ranked_records[0] in truth for o, truth in ranking),
                len(ranking),
            ),
            "at_k": ranking_metrics,
        },
        "decisions": {
            "status_accuracy": _divide(sum(o.status == o.expected_status for o in observations), len(observations)),
            "action_set_accuracy": _divide(
                sum(set(o.actions) == set(o.expected_actions) for o in observations), len(observations)
            ),
            "review_accuracy": _divide(sum(o.review_required == o.expected_review for o in observations), len(observations)),
            "uncertain_cases": len(uncertain),
            "uncertainty_detection_rate": _divide(sum(o.review_required for o in uncertain), len(uncertain)),
            "ambiguity_status_recall": _divide(
                sum(o.expected_status == "AMBIGUOUS_MATCH" and o.status == "AMBIGUOUS_MATCH" for o in observations),
                sum(o.expected_status == "AMBIGUOUS_MATCH" for o in observations)),
            "review_rate": _divide(sum(o.review_required for o in observations), len(observations)),
            "abstention_rate": _divide(sum(o.selected_record is None for o in observations), len(observations)),
            "false_automatic_matches": sum(
                o.selected_record is not None and not o.review_required
                and (not o.identity_evaluable or o.selected_record not in o.expected_records)
                for o in observations
            ),
            "false_create_proposals": sum(
                "CREATE_RECORD_CANDIDATE" in o.actions
                and (bool(o.expected_records) or "CREATE_RECORD_CANDIDATE" not in o.expected_actions)
                for o in observations
            ),
            "status_confusion": [
                {"expected": expected, "predicted": predicted, "count": count}
                for (expected, predicted), count in sorted(confusion.items())
            ],
        },
        "deltas": _prf(delta_tp, delta_fp, delta_fn),
        "volume": {
            "supplied_inventory_rows": sum(o.supplied_records for o in observations),
            "examined_rows": sum(o.examined_records for o in observations),
            "document_fields": sum(o.supplied_fields for o in observations),
        },
        "timings": {
            stage: _timing_summary([value for o in observations for value in o.timings_ms.get(stage, [])])
            for stage in stages
        },
    }
