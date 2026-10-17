"""python -m scripts.audit_inventory_numbers --output evaluation/results/inventory_number_audit.json"""
import argparse
import json
from pathlib import Path

from app.record_matching.inventory_audit import audit_inventory_numbers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-limit", type=int, default=50)
    args = parser.parse_args()
    try:
        report = audit_inventory_numbers(sample_limit=args.sample_limit)
    except Exception as exc:
        report = {"audit_completed": False, "exception_type": type(exc).__name__,
                  "message": "Az audit nem fejeződött be; nincs új bizonyíték az adatbázis egyediségére."}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0 if report.get("migration_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
