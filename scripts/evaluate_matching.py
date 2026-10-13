"""Run with: python -m scripts.evaluate_matching --repeats 5"""
import argparse
import json
from pathlib import Path

from app.evaluation.runner import run_evaluation


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=root / "tests/fixtures/matching_evaluation.json")
    parser.add_argument("--output", type=Path, default=root / "evaluation/results")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    report = run_evaluation(args.dataset, args.output, args.repeats)
    print(json.dumps(report["metrics"]["test"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
