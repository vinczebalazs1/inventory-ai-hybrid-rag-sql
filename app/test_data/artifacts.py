"""Canonical CSV/JSON bundle and tamper-evident metadata. Timestamps are not hashed."""
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from .generator import generate
from .models import COLUMNS, INTEGER_COLUMNS, GenerationConfig, InventoryRow, VERSION, MINIMUM_DATE, REFERENCE_DATE
from .validation import require_valid

ROOT = Path(__file__).resolve().parents[2]


def schema_hash() -> str:
    content = json.loads((ROOT / "config/schema.json").read_text(encoding="utf-8"))
    return sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_hashes() -> tuple[str, dict[str, str]]:
    paths = sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
    paths += sorted((ROOT / "config").glob("*")) + sorted((ROOT / "migrations").rglob("*.sql"))
    paths += [ROOT / "requirements.txt", ROOT / "requirements-dev.txt"]
    manifest = {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                for path in paths if path.is_file()}
    return sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(), manifest


def canonical_bytes(rows: list[InventoryRow]) -> bytes:
    ordered = sorted(rows, key=lambda row: row.inventory_number)
    return (json.dumps([row.model_dump() for row in ordered], ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def dataset_hash(rows: list[InventoryRow]) -> str:
    return sha256(canonical_bytes(rows)).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def export_dataset(output: Path, config: GenerationConfig) -> dict:
    rows = generate(config)
    quality = require_valid(rows, config)
    output.mkdir(parents=True, exist_ok=True)
    (output / "inventory.json").write_bytes(canonical_bytes(rows))
    with (output / "inventory.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row.model_dump() for row in sorted(rows, key=lambda r: r.inventory_number))
    manifest = {"dataset_version": VERSION, "generator_version": VERSION,
        "random_seed": config.seed, "record_count": config.count,
        "schema_version": "inventory_items_11_v1",
        "schema_sha256": schema_hash(),
        "generation_config": config.model_dump(mode="json"),
        "generation_policy": {"minimum_date": MINIMUM_DATE.isoformat(), "reference_date": REFERENCE_DATE.isoformat(),
            "depreciation": "purchase * min(age_days, catalog_useful_life_days) // catalog_useful_life_days",
            "currency": "HUF", "price_unit": "synthetic integer HUF; not market prices"},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_dataset_sha256": dataset_hash(rows), "quality": quality,
        "files": {name: sha256((output / name).read_bytes()).hexdigest() for name in ("inventory.json", "inventory.csv")}}
    # The document manifest is separate so installing document-generation libraries
    # is optional for pure database workflows; both refer to the same data hash.
    write_json(output / "manifest.json", manifest)
    return manifest


def read_bundle(directory: Path, *, expected_count: int = 1000) -> tuple[list[InventoryRow], GenerationConfig, dict]:
    for name in ("manifest.json", "inventory.json", "inventory.csv"):
        if (directory / name).stat().st_size > 100_000_000:
            raise ValueError("Dataset file exceeds the 100 MB safety limit")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_version"] != VERSION or manifest["generator_version"] != VERSION:
        raise ValueError("Unsupported dataset/generator version")
    config = GenerationConfig.model_validate_json(json.dumps(manifest["generation_config"]))
    if config.count != expected_count or manifest["record_count"] != config.count or manifest["random_seed"] != config.seed:
        raise ValueError("Unexpected dataset count or seed")
    if manifest["schema_version"] != "inventory_items_11_v1" or manifest["schema_sha256"] != schema_hash():
        raise ValueError("Schema manifest mismatch")
    for name in ("inventory.json", "inventory.csv"):
        if sha256((directory / name).read_bytes()).hexdigest() != manifest["files"][name]:
            raise ValueError(f"File hash mismatch: {name}")
    raw = json.loads((directory / "inventory.json").read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != config.count:
        raise ValueError("Unexpected JSON record count")
    rows = [InventoryRow.model_validate(row) for row in raw]
    with (directory / "inventory.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError("CSV columns differ from the schema")
        csv_rows = [InventoryRow.model_validate({k: int(v) if k in INTEGER_COLUMNS else v for k, v in row.items()}) for row in reader]
    quality = require_valid(rows, config)
    if (dataset_hash(rows) != manifest["canonical_dataset_sha256"] or canonical_bytes(csv_rows) != canonical_bytes(rows)
            or canonical_bytes(generate(config)) != canonical_bytes(rows) or manifest["quality"] != quality):
        raise ValueError("Dataset, CSV, generation config or manifest mismatch")
    return rows, config, manifest
