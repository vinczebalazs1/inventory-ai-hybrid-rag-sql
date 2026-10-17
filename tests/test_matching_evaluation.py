from pathlib import Path
import csv
import json

from app.evaluation.dataset import load_dataset
from app.evaluation.runner import run_evaluation

FIXTURE = Path(__file__).parent / "fixtures/matching_evaluation.json"


def test_frozen_fixture_has_diverse_disjoint_calibration_and_test_cases():
    dataset = load_dataset(FIXTURE)
    test = [case for case in dataset.cases if case.split == "test"]
    calibration = [case for case in dataset.cases if case.split == "calibration"]
    assert len(test) >= 40 and len(calibration) >= 5
    assert len({case.category for case in test}) >= 25
    assert not {case.id for case in test} & {case.id for case in calibration}


def test_evaluation_runs_both_strategies_and_writes_computable_outputs(tmp_path):
    report = run_evaluation(FIXTURE, tmp_path, repeats=2)
    assert report["dataset_cases"] == 74
    assert len(report["dataset_sha256"]) == 64
    loaded = json.loads((tmp_path / "matching_metrics.json").read_text(encoding="utf-8"))
    assert loaded == report
    for strategy in ("exact_only", "hybrid"):
        metrics = report["metrics"]["test"][strategy]
        assert metrics["cases"] == 64
        assert metrics["decisions"]["false_automatic_matches"] == 0
        assert metrics["decisions"]["false_create_proposals"] == 0
        assert metrics["timings"]["total"]["samples"] == 128
        assert metrics["timings"]["total"]["p95_ms"] is not None
    with (tmp_path / "matching_cases.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 148
