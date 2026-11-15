"""Real Docling exports, explicitly stubbed LLM responses, no external services."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.document_processing import processing_service
from app.document_processing.config import Settings
from app.document_processing.docling_parser import parse_document
from app.document_processing.field_mapper import map_fields
from app.document_processing.models import ExtractedField, ExtractionResult, ParsedDocument
from app.document_processing.validation_service import validate_fields
from app.record_matching.models import ActionType, ComparisonStatus, MatchStatus
from app.record_matching.preparation import _asset_table
from app.record_matching.reconciliation_service import reconcile_document
from app.services import llm_service
from app.services.schema_service import load_schema
from app.test_data.evaluation import assess, fixture_repository
from app.test_data.models import InventoryRow

ROOT = Path(__file__).resolve().parents[1]


def _repository():
    return fixture_repository([InventoryRow.model_validate(row) for row in
                               json.loads((ROOT / "data/synthetic/inventory.json").read_text(encoding="utf-8"))])


def _stub_llm(monkeypatch, fields):
    targets = {field["label"]: field["expected_target"] for field in fields}

    def reply(text, model):
        if "Document chunk:\n" in text:
            page = json.loads(text.split("Parser page metadata (null means unavailable): ")[1].splitlines()[0])
            return json.dumps({"fields": [{k: v for k, v in field.items() if k != "expected_target"}
                                         for field in fields if page is None or field["page"] == page]})
        mapped = json.loads(text.split("Extracted fields with indexes: ")[1])
        return json.dumps({"assignments": [{"index": f["index"], "target_field": targets[f["label"]]} for f in mapped]})

    mock = Mock(side_effect=reply)
    monkeypatch.setattr(llm_service, "ask_llm", mock)
    return mock


@pytest.mark.parametrize("money_space", [None, " ", "\u00a0", "\u202f"],
                         ids=["bare-amount", "ft-space", "ft-nbsp", "ft-narrow-nbsp"])
def test_five_page_single_asset_repeats_and_calculation(monkeypatch, money_space):
    fixture = json.loads((ROOT / "tests/fixtures/detailed_single_asset.json").read_text(encoding="utf-8"))
    financial = {"purchase_value": 326000, "depreciation": 171306, "current_value": 154694}
    if money_space is not None:
        for field in fixture["fields"]:
            if field["expected_target"] in financial:
                field["value"] = field["value"].replace(" ", money_space) + money_space + "Ft"
                field["evidence"] = field["label"] + "\n\n" + field["value"]
    pages = {int(n): text for n, text in fixture["pages"].items()}
    text = "\n\n".join(pages.values())
    parsed = ParsedDocument(source_name=fixture["source_name"], source_extension=".pdf",
                            markdown=text, extraction_text=text, pages=pages)
    monkeypatch.setattr(processing_service, "parse_document", lambda *a, **k: parsed)
    _stub_llm(monkeypatch, fixture["fields"])
    processing = processing_service.process_document(b"stubbed parser; real saved exports", parsed.source_name)
    result = reconcile_document(processing, repository=_repository())
    assert not processing.validation_issues
    assert not result.validation_summary.issues
    assert not result.validation_summary.missing_evidence_fields
    assert not result.warnings
    assert result.match_status == MatchStatus.EXACT_MATCH
    assert result.matched_record.values["inventory_number"] == "L-00001"
    assert not result.prepared_document.possible_multiple_entities
    assert not result.review_required
    assert all(c.status == ComparisonStatus.EQUAL for c in result.field_comparisons)
    assert [a.action_type for a in result.suggested_actions] == [ActionType.ATTACH_DOCUMENT]
    money = [f for f in processing.mapping.mapped_fields if f.target_field in financial]
    assert {f.target_field: f.normalized_value for f in money} == financial
    assert all(f.page == 1 for f in money)
    for field in money:
        original = next(f for f in fixture["fields"] if f["expected_target"] == field.target_field)
        assert field.raw_value == original["value"] and field.evidence == original["evidence"]
    # The minus/ratio are retained for inspection, not rewritten or lost.
    assert {(f.value, f.value_origin) for f in processing.mapping.unmapped_fields} >= {
        ("-171 306", "calculation"), ("52,55%", "calculation")}


def test_docling_exports_text_children_inside_picture_on_each_page():
    from docling.datamodel.base_models import ConversionStatus
    from docling_core.types.doc import (BoundingBox, DocItemLabel, DoclingDocument,
                                       ProvenanceItem, Size)
    document = DoclingDocument(name="financial-card")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    text = "FELHALMOZOTT ÉCS.: 171 306 Ft"
    prov = ProvenanceItem(page_no=1, bbox=BoundingBox(l=1, t=1, r=100, b=100), charspan=(0, len(text)))
    picture = document.add_picture(prov=prov)
    document.add_text(label=DocItemLabel.TEXT, text=text, parent=picture, prov=prov)
    assert text not in document.export_to_markdown()
    converter = Mock()
    converter.convert.return_value = SimpleNamespace(status=ConversionStatus.SUCCESS, document=document)
    parsed = parse_document(b"converter fixture", "card.pdf", converter=converter)
    assert text in parsed.markdown and text in parsed.pages[1] and text in parsed.extraction_text


@pytest.mark.parametrize("value, expected", [("-171306", -171306), ("-171 306", -171306),
                                            ("171306", 171306), ("-171 306 Ft", -171306)])
def test_recorded_signed_amount_is_never_absolute_valued(monkeypatch, value, expected):
    source = ExtractionResult(source_name="signed.pdf", fields=[ExtractedField(
        label="Depreciation", value=value, evidence=f"Depreciation: {value}")])
    mock = Mock(return_value=json.dumps({"assignments": [{"index": 0, "target_field": "depreciation"}]}))
    monkeypatch.setattr(llm_service, "ask_llm", mock)
    mapping = map_fields(source, load_schema()["inventory_items"], {}, Settings())
    assert not validate_fields(mapping, load_schema()["inventory_items"])
    assert mapping.mapped_fields[0].raw_value == value
    assert mapping.mapped_fields[0].normalized_value == expected
    assert "Depreciation: " in mock.call_args.args[0]  # mapper receives evidence


def test_calculation_only_is_not_promoted_to_recorded_financial_value(monkeypatch):
    no_call = Mock(side_effect=AssertionError("Calculation needs no mapping call"))
    monkeypatch.setattr(llm_service, "ask_llm", no_call)
    field = ExtractedField(label="Depreciation", value="-171306", value_origin="calculation",
                           evidence="326000 - 171306 = 154694")
    mapping = map_fields(ExtractionResult(source_name="calculation.pdf", fields=[field]),
                         load_schema()["inventory_items"], {}, Settings())
    assert not mapping.mapped_fields and mapping.unmapped_fields == [field]
    no_call.assert_not_called()


def test_conflicting_recorded_amounts_still_require_review(monkeypatch):
    from app.document_processing.models import ProcessingResult
    fields = [
        {"label": "Inventory number", "value": "L-00001", "expected_target": "inventory_number"},
        {"label": "Depreciation", "value": "171306", "expected_target": "depreciation"},
        {"label": "Depreciation", "value": "-171306", "expected_target": "depreciation"},
    ]
    for field in fields:
        field.update(page=1, evidence=f"{field['label']}: {field['value']}")
    _stub_llm(monkeypatch, fields)
    source = ExtractionResult(source_name="conflict.pdf", fields=[
        ExtractedField(**{k: v for k, v in f.items() if k != "expected_target"}) for f in fields])
    mapping = map_fields(source, load_schema()["inventory_items"], {}, Settings())
    text = "\n".join(f["evidence"] for f in fields)
    processing = ProcessingResult(
        parsed_document=ParsedDocument(source_name=source.source_name, source_extension=".pdf",
                                       markdown=text, extraction_text=text, pages={1: text}),
        extraction=source, mapping=mapping,
        validation_issues=validate_fields(mapping, load_schema()["inventory_items"]),
    )
    repository = _repository()
    result = reconcile_document(processing, repository=repository)
    assert result.match_status == MatchStatus.CONFLICTING_DATA
    assert result.review_required
    assert result.identified_record.values["inventory_number"] == "L-00001"
    assert result.counts.internal_conflict_fields == 1
    assert not result.prepared_document.possible_multiple_entities
    assert all(a.action_type == ActionType.MANUAL_REVIEW for a in result.suggested_actions)


@pytest.mark.parametrize("table, multiple", [
    ("| PARAMÉTER | GYÁRTÓI MODELLJELLEMZŐ / LEHETSÉGES OPCIÓ |\n|---|---|\n| RAM | 64 GB |\n| CPU | Intel |", False),
    ("| Eszköz | Leltári szám |\n|---|---|\n| Dell | L-1 |\n| Dell | L-2 |", True),
    ("| Eszköz | Leltári szám |\n|---|---|\n| Dell | L-1 |\n| Dell | L-1 |", False),
    ("| Eszköz | Leltári szám | Helyszín |\n|---|---|---|\n| Dell | L-1 | LIB |\n| Dell | L-1 | NIK |", False),
    ("| Model | Item code |\n|---|---|\n| Dell | LAT5540 |\n| Dell | LAT5540 |", True),
    ("| Eszköz | Leltári szám |\n|---|---|\n| Dell | L-1 |\n| Dell | l-1 |", True),
    ("| Eszköz | Leltári szám |\n|---|---|\n| Dell | L-1 |\n| Dell | |", True),
    ("| Mező | Érték |\n|---|---|\n| Leltári szám | L-1 |\n| Leltári szám | L-1 |", False),
    ("| Mező | Érték |\n|---|---|\n| Leltári szám | L-1 |\n| Leltári szám | L-2 |", True),
    ("| Cikkszám | Leltári szám |\n|---|---|\n| LAT5540 | L-1 |\n| Helyszín | Darabszám |\n| LIB | 1 |", False),
    ("| Cikkszám | Leltári szám |\n|---|---|\n| LAT5540 | L-1 |\n| Cikkszám | Leltári szám |\n| LAT5540 | L-2 |", True),
])
def test_asset_tables_keep_multiple_asset_protection(table, multiple):
    assert _asset_table(table) is multiple


@pytest.mark.parametrize("document_id", ["D01", "D02"])
@pytest.mark.parametrize("extension", ["docx", "pdf"])
def test_existing_d01_d02_actual_documents(monkeypatch, request, document_id, extension):
    if extension == "pdf" and not request.config.getoption("--run-docling-pdf"):
        pytest.skip("Real PDF conversion requires --run-docling-pdf")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    truth = json.loads((ROOT / "data/synthetic/ground_truth.json").read_text(encoding="utf-8"))
    case = next(case for case in truth["scenarios"] if case["document_id"] == document_id)
    fields = [{"label": f["label"], "value": f["raw"], "page": 1,
               "evidence": f"{f['label']}: {f['raw']}", "expected_target": f["field"]}
              for f in case["expected_fields"]]
    _stub_llm(monkeypatch, fields)
    path = ROOT / f"data/synthetic/documents/{document_id}.{extension}"
    processed = processing_service.process_document(path.read_bytes(), path.name)
    result = reconcile_document(processed, repository=_repository())
    assert assess(case, result)["passed"], result.model_dump_json()
