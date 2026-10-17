"""Verify that the measured code and dataset still match the stored report."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from app.evaluation.runner import implementation_hashes


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=root / "evaluation/results/matching_metrics.json")
    parser.add_argument("--dataset", type=Path, default=root / "tests/fixtures/matching_evaluation.json")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    aggregate, manifest = implementation_hashes(root)
    valid = (aggregate == report["implementation_sha256"] and manifest == report["source_manifest"]
             and sha256(args.dataset.read_bytes()).hexdigest() == report["dataset_sha256"])
    print("Code and dataset hashes match." if valid else "Report is stale: rerun the evaluation.")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
