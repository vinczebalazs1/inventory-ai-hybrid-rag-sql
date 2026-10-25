"""Offline integrity, determinism, document ground truth and export acceptance tests."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from docx import Document
from pydantic import ValidationError
from pypdf import PdfReader
import pytest

from app.test_data.artifacts import canonical_bytes, dataset_hash, export_dataset, read_bundle
from app.test_data.catalog import BY_CODE, DISTRIBUTION
from app.test_data.documents import export_documents, read_ground_truth, scenarios
from app.test_data.generator import generate
from app.test_data.models import GenerationConfig, InventoryRow
from app.test_data.validation import require_valid, validate_rows


def test_official_dataset_distribution_physical_devices_and_repeated_types():
    config = GenerationConfig()
    rows = generate(config)
    report = require_valid(rows, config)
    assert len(rows) == len({r.inventory_number for r in rows}) == 1000
    assert rows[0].inventory_number == "L-00001" and rows[-1].inventory_number == "L-01000"
    assert all(r.quantity == 1 and r.currency == "HUF" for r in rows)
    assert report["category_counts"] == DISTRIBUTION
    assert report["repeated_item_codes"] == len(BY_CODE)
    assert all(len({r.location for r in rows if r.item_code == code}) > 1 for code in BY_CODE)
    assert all(r.name == BY_CODE[r.item_code].name for r in rows)
    assert {"Dell Latitude 5540", "Dell Latitude 5550"}.issubset(report["model_counts"])


@pytest.mark.parametrize("seed", [0, 7, 42, -100, 20261018])
def test_seed_reproducibility_and_integrity(seed):
    config = GenerationConfig(seed=seed)
    first, second = generate(config), generate(config)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert dataset_hash(first) == dataset_hash(list(reversed(first)))
    assert require_valid(first, config)["validation_passed"]
    assert dataset_hash(first) != dataset_hash(generate(GenerationConfig(seed=seed + 1)))


@pytest.mark.parametrize("count", [1, 7, 5000, 10000])
def test_experimental_counts_are_consistent_and_do_not_require_network(count):
    config = GenerationConfig(count=count, locations=("LAB", "Raktár"))
    assert require_valid(generate(config), config)["record_count"] == count


@pytest.mark.parametrize("field,value", [("inventory_number", ""), ("inventory_number", " \t"),
    ("quantity", 2), ("name", " "), ("item_code", "WRONG"), ("location", "UNKNOWN"),
    ("currency", "USD"), ("activation_date", "3026-01-01"), ("activation_date", "2026-99-99"),
    ("current_value", 1), ("depreciation", 0)])
def test_domain_validation_rejects_corruption(field, value):
    rows = generate()
    rows[0] = InventoryRow.model_validate({**rows[0].model_dump(), field: value})
    assert not validate_rows(rows, GenerationConfig())["validation_passed"]


@pytest.mark.parametrize("field,value", [("inventory_number", None), ("quantity", None),
    ("quantity", True), ("purchase_value", -1), ("purchase_value", 1.5), ("current_value", "100")])
def test_row_contract_rejects_null_or_wrong_types(field, value):
    with pytest.raises(ValidationError):
        InventoryRow.model_validate({**generate()[0].model_dump(), field: value})


def test_duplicate_is_detected_even_when_count_is_correct():
    rows = generate()
    rows[-1] = rows[0]
    report = validate_rows(rows, GenerationConfig())
    assert report["violations"]["duplicate_inventory_numbers"] == 1
    assert not report["validation_passed"]


def test_export_roundtrip_manifest_and_independent_hash(tmp_path):
    first = export_dataset(tmp_path / "a", GenerationConfig())
    second = export_dataset(tmp_path / "b", GenerationConfig())
    rows, config, manifest = read_bundle(tmp_path / "a")
    assert first["canonical_dataset_sha256"] == second["canonical_dataset_sha256"]
    assert (tmp_path / "a/inventory.csv").read_bytes() == (tmp_path / "b/inventory.csv").read_bytes()
    assert sha256((tmp_path / "a/inventory.json").read_bytes()).hexdigest() == dataset_hash(rows)
    manifest["generated_at"] = "different timestamp is deliberately outside the data hash"
    (tmp_path / "a/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert read_bundle(tmp_path / "a")[0] == rows


@pytest.mark.parametrize("name", ["inventory.csv", "inventory.json", "manifest.json"])
def test_tampered_bundle_is_rejected(tmp_path, name):
    export_dataset(tmp_path, GenerationConfig())
    path = tmp_path / name
    path.write_bytes(path.read_bytes().replace(b"L-00001", b"L-99999") if name != "manifest.json"
                     else path.read_bytes().replace(b'"random_seed": 42', b'"random_seed": 43'))
    with pytest.raises(ValueError):
        read_bundle(tmp_path)


def test_real_pdf_docx_and_independent_ground_truth_are_reproducible(tmp_path):
    manifest = export_dataset(tmp_path, GenerationConfig())
    rows, _, _ = read_bundle(tmp_path)
    truth = export_documents(tmp_path, rows, manifest)
    regenerated = export_documents(tmp_path / "repeat", rows, manifest)
    assert truth == regenerated
    assert len(truth["scenarios"]) == 16
    for case in truth["scenarios"]:
        pdf_text = "\n".join(page.extract_text() for page in PdfReader(tmp_path / f"documents/{case['document_id']}.pdf").pages)
        docx_text = "\n".join(p.text for p in Document(tmp_path / f"documents/{case['document_id']}.docx").paragraphs)
        for field in case["expected_fields"]:
            assert f"{field['label']}: {field['raw']}" in pdf_text
            assert f"{field['label']}: {field['raw']}" in docx_text
        assert case["files"] == regenerated["scenarios"][int(case["document_id"][1:]) - 1]["files"]
    assert truth["scenarios"][0]["expected_fields"][0]["value"] == rows[0].item_code
    assert truth["scenarios"][1]["expected_field_differences"][0]["database_value"] == rows[0].location
    assert len({f["raw"] for f in truth["scenarios"][14]["expected_fields"] if f["field"] == "inventory_number"}) == 2
    _, _, manifest = read_bundle(tmp_path)
    assert read_ground_truth(tmp_path, manifest) == truth


def test_evaluation_reports_disagreement_without_relabelling_expected_results():
    from app.test_data.evaluation import evaluate
    rows = generate()
    truth = {"scenarios": scenarios(rows)}
    original = deepcopy(truth)
    report = evaluate(rows, truth)
    assert truth == original and len(report["cases"]) == 16
    assert report["passed"] + report["failed"] == 16
    assert report["cases"][0]["passed"]
    changed = deepcopy(truth)
    changed["scenarios"][0]["expected_match_category"] = "NO_MATCH"
    assert not evaluate(rows, changed)["cases"][0]["passed"]


def test_committed_artifacts_match_generator():
    directory = Path(__file__).resolve().parents[1] / "data/synthetic"
    rows, config, manifest = read_bundle(directory)
    assert canonical_bytes(rows) == canonical_bytes(generate(config))
    assert len(read_ground_truth(directory, manifest)["scenarios"]) == 16
