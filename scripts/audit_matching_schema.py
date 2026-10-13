"""Inspect matching schema without reading business records or changing the DB."""
import argparse
import json
from pathlib import Path

from app.record_matching.config import MatchingSettings
from app.record_matching.repository import InventoryRepository
from app.services.schema_service import load_schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    settings = MatchingSettings.from_env()
    columns = {column["column"]: column["type"] for column in load_schema()[settings.target_table]}
    result = InventoryRepository().inspect_schema(columns, settings)
    report = result.model_dump_json(indent=2)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    return 0 if result.compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())
