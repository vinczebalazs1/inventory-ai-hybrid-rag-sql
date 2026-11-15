"""Field deltas retain provenance and never interpret absence as deletion."""
from .models import CandidateRecord, ComparisonStatus as Status, FieldComparison, PreparedDocument
from .normalization import comparison_value
from .config import IDENTIFIER_FIELDS
from app.document_processing.models import Occurrence

MONEY_FIELDS = frozenset(("purchase_value", "depreciation", "current_value"))


def _same_currency(document: PreparedDocument, record: CandidateRecord) -> bool:
    try:
        left = comparison_value(document.values.get("currency"), "text", "currency")
        right = comparison_value(record.values.get("currency"), "text", "currency")
        return left is not None and left == right
    except (ValueError, TypeError):
        return False


def compare_fields(document: PreparedDocument, record: CandidateRecord,
                   columns: dict[str, str]) -> list[FieldComparison]:
    comparisons = []
    for name, dtype in columns.items():
        origins = [field for field in document.fields if field.target_field == name]
        if not origins:
            comparisons.append(FieldComparison(field=name, database_value=record.values.get(name),
                               record_id=record.record_id, candidate_rank=record.rank, status=Status.UNKNOWN,
                               explanation="A dokumentumból hiányzó mező nem jelent eltérést vagy törlést."))
            continue
        for origin in origins:
            comparison = FieldComparison(field=name, source_label=origin.source_label,
                raw_document_value=origin.raw_value, normalized_document_value=origin.normalized_value,
                database_value=record.values.get(name), record_id=record.record_id,
                candidate_rank=record.rank,
                evidence=origin.evidence, page=origin.page, status=Status.NOT_COMPARABLE, explanation="",
                validation_status=origin.validation_status,
                **{key: getattr(origin, key) for key in Occurrence.model_fields})
            if origin.extraction_uncertain:
                comparison.status, comparison.explanation = Status.UNCERTAIN, origin.uncertainty_reason or "Bizonytalan kinyerés; nem igazolt mezőeltérés."
            elif origin.validation_status == "CONFLICT":
                comparison.status, comparison.explanation = Status.INTERNAL_CONFLICT, "Dokumentumon belüli ellentmondás; egyik előfordulás sem minősül automatikusan aktuálisnak."
            elif origin.validation_status in ("INVALID", "UNPARSEABLE"):
                comparison.status, comparison.explanation = Status.INVALID, origin.explanation or "Ellentmondó dokumentumadat."
            elif origin.validation_status != "VALID":
                comparison.explanation = origin.explanation or "Kifejezett üres/null vagy nem támogatott adat; törlés nem javasolható."
            elif not origin.evidence:
                comparison.status, comparison.explanation = Status.UNCERTAIN, "Nincs visszakereshető bizonyíték; nem igazolt mezőeltérés."
            elif name not in record.values:
                comparison.explanation = "A mező nem érhető el a keresési eredményben."
            elif name in MONEY_FIELDS and not _same_currency(document, record):
                comparison.explanation = "Az összeg csak igazoltan egyező pénznemben hasonlítható össze."
            else:
                try:
                    db_value = (record.values[name] if name in IDENTIFIER_FIELDS else
                                comparison_value(record.values[name], dtype, name))
                    comparison.normalized_database_value = db_value
                    comparison.status = Status.UNKNOWN if db_value is None else Status.EQUAL if origin.comparison_value == db_value else Status.DIFFERENT
                    comparison.explanation = "Normalizált értékek egyeznek." if comparison.status == Status.EQUAL else (
                        "Az adatbázis NULL értéke ismeretlen; önmagában nem igazol tényleges értékváltozást." if db_value is None else "Az értékek eltérnek.")
                    if comparison.status == Status.DIFFERENT and origin.extraction_method == "ocr":
                        comparison.status = Status.UNCERTAIN
                        comparison.explanation = "Az OCR-érték eltér a rekordtól; az eredeti kép ellenőrzéséig nem igazolt mezőváltozás. Az értéket nem javítottuk át."
                except (ValueError, TypeError):
                    comparison.explanation = "Az adatbázisérték nem normalizálható biztonságosan."
            comparisons.append(comparison)
    return comparisons
