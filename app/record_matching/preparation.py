"""Turn the existing flat mapping into one safe entity, retaining every origin."""
from collections import defaultdict
import re

from app.document_processing.models import ProcessingResult
from .config import IDENTIFIER_FIELDS, MatchingSettings
from .models import PreparedDocument, PreparedField, ValidationIssue
from .normalization import comparison_value, raw_comparison_value, text_key


def _asset_table(markdown: str) -> bool:
    """Conservative guard for repeated asset rows; attribute/value tables are excluded."""
    lines = markdown.splitlines()
    headers = ("inventory", "leltári", "leltari", "item_code", "cikkszám", "cikkszam",
               "serial", "sorozatszám", "service tag", "eszköz", "device", "modell", "model", "name", "megnevezés")
    for index, line in enumerate(lines[:-1]):
        if "|" not in line or not re.fullmatch(r"[\s|:\-]+", lines[index + 1]):
            continue
        cells = [text_key(cell) for cell in line.strip().strip("|").split("|")]
        if not any(any(header in cell for header in headers) for cell in cells):
            continue
        rows = 0
        for row in lines[index + 2:]:
            if "|" not in row or not row.strip():
                break
            rows += 1
        if rows > 1:
            return True
    return False


def prepare_document(result: ProcessingResult, columns: dict[str, str],
                     settings: MatchingSettings) -> PreparedDocument:
    prepared = PreparedDocument(validation_issues=list(result.validation_issues),
                                unmapped_count=len(result.mapping.unmapped_fields))
    issues = {issue.field for issue in result.validation_issues}
    grouped: dict[str, list[PreparedField]] = defaultdict(list)
    for original in result.mapping.mapped_fields:
        item = PreparedField(**original.model_dump(), validation_status="VALID")
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
                item.validation_status = "EXPLICIT_EMPTY"
                item.explanation = "Kifejezett üres/null adat; nem jelent törlési szándékot."
            elif field in issues or item.normalized_value is None:
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
                grouped[field].append(item)
        except (ValueError, TypeError) as exc:
            if item.validation_status != "UNSUPPORTED":
                item.validation_status = "INVALID"
            item.explanation = str(exc)
            # An invalid supplied identifier cannot be silently ignored in favour
            # of an otherwise exact secondary key.
            if field in IDENTIFIER_FIELDS:
                prepared.blocked = True
            prepared.validation_issues.append(ValidationIssue(field=field, severity="warning", message=str(exc)))
        prepared.fields.append(item)

    for field, occurrences in grouped.items():
        distinct = {item.comparison_value for item in occurrences}
        if len(distinct) > 1:
            prepared.blocked = True
            prepared.possible_multiple_entities = True
            prepared.reasons.append(f"{field}: több eltérő érték; a mezők nem egyesíthetők egy rekordba.")
            for item in occurrences:
                item.validation_status = "CONFLICT"
        else:
            # Search receives validated original form. Case-folding belongs to comparison only.
            prepared.values[field] = (occurrences[0].comparison_value if field in IDENTIFIER_FIELDS
                                      else occurrences[0].normalized_value)
    if _asset_table(result.parsed_document.markdown):
        prepared.blocked = True
        prepared.possible_multiple_entities = True
        prepared.reasons.append("Több eszközsor található a táblázatban; a lapos mezőlista nem csoportosítható biztonságosan.")
    entity_labels: dict[str, set[str]] = defaultdict(set)
    for field in result.extraction.fields + result.mapping.unmapped_fields:
        label = text_key(field.label)
        if any(token in label for token in ("serial", "sorozatsz", "service tag", "inventory number", "leltári szám")):
            entity_labels[label].add(field.value.strip())
    if any(len(values) > 1 for values in entity_labels.values()):
        prepared.blocked = prepared.possible_multiple_entities = True
        prepared.reasons.append("Több különböző eszközazonosító található a kinyert mezők között.")
    for field in prepared.fields:
        if field.validation_status == "EXPLICIT_EMPTY" and field.target_field in prepared.values:
            prepared.blocked = True
            prepared.reasons.append(f"{field.target_field}: kitöltött és kifejezetten üres érték is szerepel.")
    if prepared.blocked and not prepared.reasons:
        prepared.reasons.append("Azonosító-megfeleltetési ellentmondás; emberi ellenőrzés szükséges.")
    return prepared
