"""Verify clean dataset/documents and recorded source hashes without external services."""
import argparse
import json
from pathlib import Path

from app.test_data.artifacts import read_bundle, source_hashes
from app.test_data.documents import read_ground_truth


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--reports", type=Path, default=Path("evaluation/clean_inventory"))
    args = parser.parse_args(argv)
    try:
        _, _, manifest = read_bundle(args.dataset)
        read_ground_truth(args.dataset, manifest)
        implementation, _ = source_hashes()
        results = {}
        for name in ("matching_offline.json", "matching_postgres.json", "postgres_verification.json", "scalability.json"):
            report = json.loads((args.reports / name).read_text(encoding="utf-8"))
            results[name] = report["implementation_sha256"] == implementation
            if "canonical_dataset_sha256" in report:
                results[name] &= report["canonical_dataset_sha256"] == manifest["canonical_dataset_sha256"]
        print(json.dumps({"dataset_and_documents_verified": True, "current_source_matches": results}, indent=2))
        return 0 if all(results.values()) else 1
    except Exception as exc:
        print(json.dumps({"verification_completed": False, "exception_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
