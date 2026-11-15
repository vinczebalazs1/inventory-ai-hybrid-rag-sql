"""Turn the existing flat mapping into one safe entity, retaining every origin."""
from collections import defaultdict
from decimal import Decimal, localcontext
import re

from app.document_processing.models import ProcessingResult
from app.document_processing.field_labels import canonical_label
from .config import IDENTIFIER_FIELDS, MatchingSettings
from .models import PreparedDocument, PreparedField, ValidationIssue
from .normalization import comparison_value, identifier_key, raw_comparison_value, text_key


def _header_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", text_key(value))


# Whole labels, not substrings: "gyártói modelljellemző" is not a model column.
_TABLE_LABELS = {
    _header_key(label): field for field, labels in {
        "inventory_number": ("inventory_number", "inventory", "inventory no", "leltári szám", "leltari szam"),
        "item_code": ("item_code", "item code", "cikkszám", "cikkszam"),
        "serial": ("serial", "serial number", "sorozatszám", "sorozatszam", "service tag"),
        "name": ("name", "asset name", "device name", "eszköz", "device", "modell", "model", "megnevezés", "eszköz megnevezése"),
        "sub_code": ("sub_code", "alszám"),
        "activation_date": ("activation_date", "activation date", "aktiválás dátuma"),
        "location": ("location", "helyszín"),
        "currency": ("currency", "pénznem"),
        "quantity": ("quantity", "darabszám", "mennyiség"),
        "purchase_value": ("purchase_value", "purchase value", "beszerzési érték"),
        "depreciation": ("depreciation", "értékcsökkenés", "felhalmozott écs"),
        "current_value": ("current_value", "current value", "jelenlegi érték"),
    }.items() for label in labels
}
_ENTITY_COLUMNS = {"inventory_number", "item_code", "serial", "name"}
_UNIQUE_COLUMNS = {"inventory_number", "serial"}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _form_labels(cells: list[str]) -> bool:
    keys = [_header_key(cell) for cell in cells if cell.strip()]
    return (sum(key in _TABLE_LABELS for key in keys) >= 2
            and all(key in _TABLE_LABELS or key in {"forrás", "minta", "source"} for key in keys))


def _conflicting_form_identifiers(pairs) -> bool:
    values: dict[str, set[str]] = defaultdict(set)
    for label, value in pairs:
        field = _TABLE_LABELS.get(_header_key(label))
        if field in _ENTITY_COLUMNS and value.strip():
            values[field].add(identifier_key(value) if field != "name" else text_key(value))
    if len(values.get("inventory_number", set())) == 1:
        return False
    return any(len(items) > 1 for items in values.values())


def _asset_table(markdown: str) -> bool:
    """Conservative guard for repeated asset rows; attribute/value tables are excluded."""
    lines = markdown.splitlines()
    for index, line in enumerate(lines[:-1]):
        if "|" not in line or not re.fullmatch(r"[\s|:\-]+", lines[index + 1]):
            continue
        cells = _cells(line)
        rows = []
        for row in lines[index + 2:]:
            if "|" not in row or not row.strip():
                break
            rows.append(_cells(row))
        if not rows:
            continue
        # A two-column form can start with an actual field/value as its header.
        # It is not an asset list just because the first cell says "name".
        if (len(cells) == 2 and canonical_label(cells[0]) and not canonical_label(cells[1])
                and all(len(row) == 2 and canonical_label(row[0]) for row in rows)):
            if _conflicting_form_identifiers([tuple(cells), *(tuple(row) for row in rows)]):
                return True
            continue
        # Attribute/value tables can still contain genuinely conflicting IDs.
        if _header_key(cells[0]) in {"mező", "field", "attribute", "paraméter", "parameter", "jellemző"}:
            if _conflicting_form_identifiers((row[0], row[1]) for row in rows if len(row) >= 2):
                return True
            continue
        # Docling may flatten a form into alternating label/value rows. Only
        # accept that structure when every label row is recognized, not merely
        # because one row happens to contain a word such as "location".
        if (len(rows) >= 3 and len(rows) % 2 == 1 and _form_labels(cells)
                and all(len(row) == len(cells) for row in rows)
                and all(_form_labels(row) for row in rows[1::2])):
            labels = [cells, *rows[1::2]]
            if _conflicting_form_identifiers(
                    pair for header, values in zip(labels, rows[::2]) for pair in zip(header, values)):
                return True
            continue
        fields = [_TABLE_LABELS.get(_header_key(cell)) for cell in cells]
        if len(rows) <= 1 or not any(field in _ENTITY_COLUMNS for field in fields):
            continue
        unique_indexes = [i for i, field in enumerate(fields) if field in _UNIQUE_COLUMNS]
        # Identical repetitions with the same explicit individual ID are one
        # observation. Model name/item_code alone cannot prove that two rows
        # refer to the same physical device, even when their values are equal.
        if unique_indexes and all(len(row) == len(cells) and all(row[i] for i in unique_indexes) for row in rows):
            signatures = {tuple(identifier_key(row[i]) for i in unique_indexes) for row in rows}
            if len(signatures) == 1:
                continue
        return True
    return False


def prepare_document(result: ProcessingResult, columns: dict[str, str],
                     settings: MatchingSettings, *, isolated_group: bool = False) -> PreparedDocument:
    prepared = PreparedDocument(validation_issues=list(result.validation_issues),
                                unmapped_count=len(result.mapping.unmapped_fields))
    issues = result.validation_issues
    grouped: dict[str, list[PreparedField]] = defaultdict(list)
    for original in result.mapping.mapped_fields:
        item = PreparedField(**original.model_dump(), validation_status="VALID")
        prepared.asset_group_id = item.asset_group_id or prepared.asset_group_id
        field = item.target_field
        label = text_key(item.source_label).replace("_", " ").replace("-", " ")
        try:
            if field not in columns:
                item.validation_status = "UNSUPPORTED"
                raise ValueError("A mező nem szerepel a célsémában.")
            if len(item.raw_value) > settings.max_field_length:
                raise ValueError("A mező meghaladja az egyeztetési méretkorlátot.")
            if field in IDENTIFIER_FIELDS and any(
                token in label for token in ("serial", "sorozatsz", "service tag", "szériasz")
            ):
                prepared.blocked = True
                raise ValueError("A sorozatszám vagy service tag nem igazolt belső leltári azonosító.")
            if not item.raw_value.strip() or text_key(item.raw_value) in {"null", "none"}:
                item.validation_status = "MISSING"
                item.explanation = "Kifejezett üres/null adat; nem jelent törlési szándékot."
            elif text_key(item.raw_value) in {"nem ismert", "ismeretlen", "unknown", "not known"}:
                item.validation_status = "EXPLICIT_UNKNOWN"
                item.explanation = "A dokumentum kifejezetten ismeretlennek jelöli az értéket; nincs kitölthető vagy törlendő adat."
            elif (any(issue.field == field and (issue.occurrence_id == item.occurrence_id if issue.occurrence_id
                      else item.normalization_status is None) for issue in issues) or item.normalized_value is None):
                if item.normalization_status == "UNPARSEABLE":
                    item.validation_status = "UNPARSEABLE"
                raise ValueError("A korábbi validáció nem adott felhasználható mezőértéket.")
            else:
                item.comparison_value = comparison_value(item.normalized_value, columns[field], field)
                if item.comparison_value != raw_comparison_value(item.raw_value, columns[field], field):
                    raise ValueError("A normalizált érték nem vezethető le az eredeti mezőértékből.")
                evidence_source = result.parsed_document.extraction_text
                if item.page is not None and result.parsed_document.pages:
                    evidence_source = result.parsed_document.pages.get(item.page, "")
                if (not item.evidence or text_key(item.evidence) not in text_key(evidence_source)
                        or text_key(item.raw_value) not in text_key(item.evidence)):
                    item.evidence = None
                    prepared.warnings.append(f"{field}: hiányzó vagy nem visszakereshető dokumentumbeli bizonyíték.")
                if item.extraction_uncertain:
                    prepared.warnings.append(f"{field}: bizonytalan kinyerés; nem használható igazolt értékként.")
                    if field in IDENTIFIER_FIELDS:
                        prepared.blocked = True
                else:
                    grouped[field].append(item)
        except (ValueError, TypeError) as exc:
            if item.validation_status not in {"UNSUPPORTED", "UNPARSEABLE"}:
                item.validation_status = "INVALID"
            item.explanation = str(exc)
            # An invalid supplied identifier cannot be silently ignored in favour
            # of an otherwise exact secondary key.
            if field in IDENTIFIER_FIELDS:
                prepared.blocked = True
            if not any(i.occurrence_id == item.occurrence_id and i.field == field for i in prepared.validation_issues):
                prepared.validation_issues.append(ValidationIssue(field=field, severity="warning", message=str(exc),
                    occurrence_id=item.occurrence_id, raw_value=item.raw_value, page=item.page,
                    asset_group_id=item.asset_group_id))
        prepared.fields.append(item)

    for field, occurrences in grouped.items():
        distinct = {item.comparison_value for item in occurrences}
        if len(distinct) > 1:
            prepared.internal_conflicts.append(field)
            if field in IDENTIFIER_FIELDS:
                prepared.blocked = True
            prepared.reasons.append(f"{field}: dokumentumon belüli ellentmondás; egyik érték sem választható automatikusan.")
            for item in occurrences:
                item.validation_status = "CONFLICT"
        else:
            # Search receives validated original form. Case-folding belongs to comparison only.
            prepared.values[field] = (occurrences[0].comparison_value if field in IDENTIFIER_FIELDS
                                      else occurrences[0].normalized_value)
    if not isolated_group and _asset_table(result.parsed_document.markdown):
        prepared.blocked = True
        prepared.possible_multiple_entities = True
        prepared.reasons.append("Több eszközsor található a táblázatban; a lapos mezőlista nem csoportosítható biztonságosan.")
    entity_labels: dict[str, set[str]] = defaultdict(set)
    for field in result.extraction.fields + result.mapping.unmapped_fields:
        label = text_key(field.label)
        if any(token in label for token in ("serial", "sorozatsz", "service tag", "inventory number", "leltári szám")):
            entity_labels[label].add(field.value.strip())
    if not isolated_group and any(len(values) > 1 for values in entity_labels.values()):
        prepared.blocked = prepared.possible_multiple_entities = True
        prepared.reasons.append("Több különböző eszközazonosító található a kinyert mezők között.")
    for field in prepared.fields:
        if field.validation_status in {"EXPLICIT_EMPTY", "MISSING", "EXPLICIT_UNKNOWN"} and field.target_field in prepared.values:
            # An unknown observation is retained, never interpreted as deletion.
            prepared.reasons.append(f"{field.target_field}: kitöltött és kifejezetten üres érték is szerepel.")
    money = ("purchase_value", "depreciation", "current_value")
    if all(name in prepared.values for name in money):
        purchase, depreciation, current = (Decimal(str(prepared.values[name])) for name in money)
        with localcontext() as context:
            context.prec = max(28, sum(len(str(v)) for v in (purchase, depreciation, current)) + 2)
            if purchase - depreciation != current:
                prepared.business_warnings.append("A dokumentum pénzügyi összefüggése nem teljesül: bekerülési érték − értékcsökkenés ≠ jelenlegi érték. Az eredeti értékek megmaradtak.")
    prepared.warnings.extend(prepared.business_warnings)
    if result.parsed_document.ocr_pages and (set(columns) - set(prepared.values)):
        prepared.extraction_review_required = True
        prepared.warnings.append("Az OCR-dokumentum nem minden mezője olvasható/hozzárendelhető biztosan; ellenőrizd az eredeti képet.")
    if prepared.blocked and not prepared.reasons:
        prepared.reasons.append("Azonosító-megfeleltetési ellentmondás; emberi ellenőrzés szükséges.")
    return prepared
