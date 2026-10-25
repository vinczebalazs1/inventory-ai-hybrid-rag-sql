"""Controlled documents and independent business expectations, derived from source rows."""
from datetime import date, datetime, timedelta
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from .artifacts import dataset_hash, write_json
from .models import VERSION

LABELS = {"inventory_number": "Leltári szám", "item_code": "Cikkszám", "sub_code": "Alszám",
    "name": "Eszköz megnevezése", "activation_date": "Aktiválás dátuma", "purchase_value": "Beszerzési érték",
    "depreciation": "Felhalmozott értékcsökkenés", "current_value": "Jelenlegi érték", "currency": "Pénznem",
    "quantity": "Darabszám", "location": "Helyszín"}


def scenarios(rows) -> list[dict]:
    if len(rows) < 1000:
        raise ValueError("Document suite requires at least the official 1000 records")
    original = rows[0].model_dump()
    second = next(r.model_dump() for r in rows[1:] if r.name == original["name"])
    accented = next(r.model_dump() for r in rows if r.location == "KANDÓ")
    definitions = []
    def add(number, title, values, status, actions, *, identity=None, differences=(), review=True, raw=None):
        fields = [{"field": key, "label": LABELS[key], "value": value,
                   "raw": (raw or {}).get(key, str(value))} for key, value in values.items()]
        definitions.append({"document_id": f"D{number:02d}", "scenario": title,
            "expected_inventory_number": identity, "expected_fields": fields,
            "expected_field_differences": [{"field": key, "database_value": original[key],
                                           "document_value": values[key]} for key in differences],
            "expected_match_category": status, "expected_suggested_actions": actions,
            "expected_review_requirement": review})
    attach = ["ATTACH_DOCUMENT"]
    update = ["ATTACH_DOCUMENT", "UPDATE_CANDIDATE", "MANUAL_REVIEW"]
    manual = ["MANUAL_REVIEW"]
    identity = original["inventory_number"]
    add(1, "Teljesen egyező leltári adatlap", original, "EXACT_MATCH", attach, identity=identity, review=False)
    new_location = "LIB" if original["location"] != "LIB" else "NIK"
    add(2, "Megváltozott helyszín", {**original, "location": new_location}, "EXACT_MATCH", update,
        identity=identity, differences=("location",))
    new_date = (date.fromisoformat(original["activation_date"]) - timedelta(days=1)).isoformat()
    add(3, "Eltérő aktiválási dátum", {**original, "activation_date": new_date}, "EXACT_MATCH", update,
        identity=identity, differences=("activation_date",))
    add(4, "Eltérő pénzügyi értékek", {**original, "purchase_value": original["purchase_value"] + 1000,
        "current_value": original["current_value"] + 1000}, "EXACT_MATCH", update, identity=identity,
        differences=("purchase_value", "current_value"))
    add(5, "Hiányzó leltári szám, több azonos típusú eszköz", {k: v for k, v in original.items() if k != "inventory_number"},
        "AMBIGUOUS_MATCH", manual)
    add(6, "Hibás cikkszám, létező leltári szám", {**original, "item_code": "HIBAS-42"}, "CONFLICTING_DATA", manual,
        differences=("item_code",))
    add(7, "Elírt név, változatlan leltári szám", {**original, "name": "Dell Latitdue 5540"},
        "EXACT_MATCH", update, identity=identity, differences=("name",))
    add(8, "Új, a katalógusban nem szereplő eszköz", {**original, "inventory_number": "L-90001",
        "item_code": "ZD421", "name": "Zebra ZD421"}, "NO_MATCH", ["CREATE_RECORD_CANDIDATE", "MANUAL_REVIEW"])
    add(9, "Azonos modell másik fizikai példánya", second, "EXACT_MATCH", attach,
        identity=second["inventory_number"], review=False)
    add(10, "Azonosításra alkalmatlan hiányos adatlap", {"location": "NIK", "quantity": 1}, "INSUFFICIENT_DATA", manual)
    add(11, "Közös cikkszám több lehetséges rekordhoz", {"item_code": original["item_code"], "sub_code": 0}, "AMBIGUOUS_MATCH", manual)
    add(12, "Leltári szám mellett kritikus modellellentmondás", {**original, "name": "Dell Latitude 5550"}, "CONFLICTING_DATA", manual,
        differences=("name",))
    formatted = {key: f"{original[key]:,}".replace(",", " ") for key in ("purchase_value", "depreciation", "current_value")}
    formatted.update(activation_date=original["activation_date"].replace("-", ".") + ".", currency="Ft")
    add(13, "Magyar dátum-, szám- és pénznemformázás", original, "EXACT_MATCH", attach,
        identity=identity, review=False, raw=formatted)
    add(14, "Érvénytelen dátum a dokumentumban", {**original, "activation_date": "2026-99-99"}, "EXACT_MATCH", manual, identity=identity)
    add(15, "Két eszköz, tilos egy rekordba összevonni", original, "CONFLICTING_DATA", manual)
    definitions[-1]["expected_fields"].extend({"field": key, "label": LABELS[key], "value": value, "raw": str(value)}
                                             for key, value in second.items())
    add(16, "Magyar címkék és ékezetes helyszín", accented, "EXACT_MATCH", attach,
        identity=accented["inventory_number"], review=False)
    return definitions


def document_lines(scenario):
    return ["InventoryAI – szintetikus leltári tesztadatlap", scenario["document_id"] + " – " + scenario["scenario"],
            "Kizárólag tesztelésre; nem igazol valós eszközmozgást.", ""] + [
        f"{field['label']}: {field['raw']}" for field in scenario["expected_fields"]]


def _docx(lines) -> bytes:
    from docx import Document
    document = Document()
    document.core_properties.created = document.core_properties.modified = datetime(2026, 9, 30)
    document.core_properties.author = "InventoryAI synthetic generator"
    for line in lines:
        document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    # DOCX ZIP timestamps otherwise vary even for unchanged XML.
    deterministic = BytesIO()
    with ZipFile(buffer) as source, ZipFile(deterministic, "w", compression=ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            info = ZipInfo(name, date_time=(2026, 9, 30, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            target.writestr(info, source.read(name))
    return deterministic.getvalue()


def _pdf(lines) -> bytes:
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    # The bundled Bitstream Vera font includes Hungarian glyphs; no OS font or download.
    font_file = Path(reportlab.__file__).parent / "fonts/Vera.ttf"
    if "InventoryVera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("InventoryVera", str(font_file)))
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(595, 842), invariant=1, pageCompression=1)
    canvas.setTitle("InventoryAI synthetic inventory document")
    canvas.setAuthor("InventoryAI synthetic generator")
    canvas.setFont("InventoryVera", 10)
    y = 800
    for line in lines:
        if y < 50:
            canvas.showPage()
            canvas.setFont("InventoryVera", 10)
            y = 800
        canvas.drawString(35, y, line)
        y -= 20
    canvas.save()
    return buffer.getvalue()


def export_documents(directory: Path, rows, dataset_manifest) -> dict:
    from importlib.metadata import version
    cases = scenarios(rows)
    document_dir = directory / "documents"
    document_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case["files"] = {}
        for suffix, render in (("docx", _docx), ("pdf", _pdf)):
            relative = f"documents/{case['document_id']}.{suffix}"
            payload = render(document_lines(case))
            (directory / relative).write_bytes(payload)
            case["files"][relative] = sha256(payload).hexdigest()
    truth = {"version": VERSION, "reference_policy": "Business expectations fixed from source data and scenario edits, never copied from matching outputs.",
             "canonical_dataset_sha256": dataset_hash(rows), "scenarios": cases}
    write_json(directory / "ground_truth.json", truth)
    dataset_manifest = {**dataset_manifest, "documents": {
        "ground_truth": "ground_truth.json", "ground_truth_sha256": sha256((directory / "ground_truth.json").read_bytes()).hexdigest(),
        "scenario_count": len(cases), "document_count": len(cases) * 2,
        "libraries": {name: version(name) for name in ("python-docx", "reportlab")}}}
    write_json(directory / "manifest.json", dataset_manifest)
    return truth


def read_ground_truth(directory: Path, manifest) -> dict:
    info = manifest["documents"]
    path = directory / "ground_truth.json"
    if sha256(path.read_bytes()).hexdigest() != info["ground_truth_sha256"]:
        raise ValueError("Ground truth hash mismatch")
    truth = json.loads(path.read_text(encoding="utf-8"))
    if truth["version"] != VERSION or truth["canonical_dataset_sha256"] != manifest["canonical_dataset_sha256"]:
        raise ValueError("Documents refer to another dataset")
    ids = [case["document_id"] for case in truth["scenarios"]]
    if ids != [f"D{number:02d}" for number in range(1, 17)] or info["scenario_count"] != 16 or info["document_count"] != 32:
        raise ValueError("The controlled suite must contain D01-D16 in two formats")
    for case in truth["scenarios"]:
        if set(case["files"]) != {f"documents/{case['document_id']}.{suffix}" for suffix in ("pdf", "docx")}:
            raise ValueError("Unexpected document files")
        for filename, digest in case["files"].items():
            target = (directory / filename).resolve()
            if not target.is_relative_to(directory.resolve()) or sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("Document path/hash mismatch")
    return truth
