"""Docling adapter. No database, LLM or frontend dependencies."""
from io import BytesIO
import logging
from pathlib import PurePosixPath
from typing import Any

from app.errors import AppError
from .config import Settings
from .models import ParsedDocument

logger = logging.getLogger(__name__)


def parse_document(
    file_bytes: bytes, filename: str, *, settings: Settings | None = None,
    converter: Any = None,
) -> ParsedDocument:
    settings = settings or Settings.from_env()
    name = PurePosixPath(filename.replace("\\", "/")).name
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise AppError("Nem támogatott fájltípus. PDF vagy DOCX szükséges.")
    if not file_bytes or len(file_bytes) > settings.max_file_bytes:
        raise AppError("A dokumentum üres vagy meghaladja a 25 MB méretkorlátot.")
    try:
        from docling.datamodel.base_models import DocumentStream, InputFormat, ConversionStatus
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        converter = converter or DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
            format_options={InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(artifacts_path=settings.artifacts_path,
                                                    generate_parsed_pages=True)
            )},
        )
        result = converter.convert(
            DocumentStream(name=name, stream=BytesIO(file_bytes)),
            max_num_pages=settings.max_pages, max_file_size=settings.max_file_bytes,
        )
        if result.status != ConversionStatus.SUCCESS:
            raise ValueError("Docling conversion did not complete successfully")
        document = result.document
        # Layout may group genuine text (e.g. financial cards) under pictures.
        # Keep those existing text children; this does not generate image descriptions.
        markdown = document.export_to_markdown(traverse_pictures=True)
        pages = {
            number: document.export_to_markdown(page_no=number, traverse_pictures=True)
            for number in sorted(document.pages)
        } if suffix == ".pdf" else {}
        text = "\n\n".join(f"[PAGE {n}]\n{value}" for n, value in pages.items()) if pages else markdown
        if not text.strip():
            raise ValueError("Document contains no extractable text")
        logger.info("Docling parse succeeded: source=%r type=%s", name, suffix)
        # Native parser/OCR observations, not inferred from Markdown or invented
        # LLM coordinates. Default OCR remains selective (not force_full_page_ocr).
        source_cells = {}
        for page in getattr(result, "pages", []) or []:
            cells = getattr(page, "cells", [])
            if cells:
                source_cells[page.page_no] = [cell.model_dump(mode="json") for cell in cells]
        ocr_pages = [n for n, cells in source_cells.items() if any(c.get("from_ocr") for c in cells)]
        return ParsedDocument(
            source_name=name, source_extension=suffix, markdown=markdown,
            extraction_text=text, pages=pages, raw_document=document.export_to_dict(),
            source_cells=source_cells, ocr_pages=ocr_pages,
        )
    except Exception as exc:
        # Exceptions from parsers/providers may embed document contents. Log only
        # exception type and stack locations, retaining details as a chained cause.
        logger.error("Docling parse failed: source=%r error=%s", name, type(exc).__name__)
        raise AppError("A Docling nem tudta feldolgozni a dokumentumot. Ellenőrizd a fájlt és a telepítést.") from exc
