"""Bind extracted occurrences to observed source spans and native parser cells."""
import re

from .models import ExtractedField, Occurrence, ParsedDocument


def spans(text: str, excerpt: str | None) -> list[tuple[int, int]]:
    if not excerpt or not excerpt.strip():
        return []
    pattern = r"\s+".join(re.escape(part) for part in excerpt.split())
    # A short value such as 0 or 1 must not acquire bogus occurrences inside a
    # price, date or identifier. The whole verbatim token remains required.
    if excerpt.strip()[0].isalnum():
        pattern = r"(?<![\w-])" + pattern
    if excerpt.strip()[-1].isalnum():
        pattern += r"(?![\w-])"
    return [match.span() for match in re.finditer(pattern, text)]


def ground(field: ExtractedField, document: ParsedDocument, page: int | None,
           chunk: str) -> ExtractedField:
    # Only the LLM's explicit uncertainty flag and verbatim excerpts are input.
    # All identities/coordinates/confidence are reconstructed from the source.
    checked = field.model_copy(update={name: default for name, default in Occurrence().model_dump().items()})
    checked.value_origin = field.value_origin
    checked.extraction_uncertain = field.extraction_uncertain
    checked.uncertainty_reason = field.uncertainty_reason if field.extraction_uncertain else None
    checked.evidence = field.evidence if spans(chunk, field.evidence) else None
    checked.page = page if checked.evidence else None
    source = document.pages.get(page, "") if page is not None else document.extraction_text
    checked.context = (field.context if spans(chunk, field.context) and
                       spans(field.context, checked.evidence) else None)
    matches = spans(source, checked.context or checked.evidence)
    if len(matches) == 1:
        checked.source_span = matches[0]
        checked.block_id = f"page:{page}:span:{matches[0][0]}:{matches[0][1]}"
    cells = document.source_cells.get(page, [])
    value = " ".join(field.value.split())
    exact = [c for c in cells if " ".join(c.get("text", "").split()) == value]
    relevant = exact or [c for c in cells if checked.evidence and spans(checked.evidence, c.get("text"))
                        and spans(c.get("text", ""), value)]
    if len(relevant) == 1:
        cell = relevant[0]
        checked.extraction_method = "ocr" if cell.get("from_ocr") else "text"
        if cell.get("rect"):
            checked.bounding_boxes = [{"page": page, "rect": cell["rect"]}]
        if cell.get("from_ocr"):
            checked.recognition_confidence = cell.get("confidence")
    elif page in document.ocr_pages:
        checked.extraction_method = "ocr"
    elif checked.evidence:
        checked.extraction_method = "text"
    tables = []
    for table in (document.raw_document or {}).get("tables", []):
        pages = {p.get("page_no") for p in table.get("prov", [])}
        if page is not None and page not in pages:
            continue
        for cell in table.get("data", {}).get("table_cells", []):
            if " ".join(cell.get("text", "").split()) == value:
                tables.append((table, cell))
    if len(tables) == 1:
        table, cell = tables[0]
        checked.table_id = table.get("self_ref")
        checked.table_row = cell.get("start_row_offset_idx")
        checked.table_column = cell.get("start_col_offset_idx")
        if cell.get("bbox"):
            checked.bounding_boxes.append({"page": page, "bbox": cell["bbox"]})
    if checked.extraction_method == "ocr" and (checked.recognition_confidence is None or
                                               checked.recognition_confidence < 0.95):
        checked.extraction_uncertain = True
        checked.uncertainty_reason = "OCR: nincs egyértelmű cellabizonyíték vagy a felismerési pontszám 0,95 alatti."
    return checked
