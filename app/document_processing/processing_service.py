"""Read-only orchestration; no persistence or inventory record matching."""
import logging
import traceback

from app.errors import AppError
from app.services import schema_service
from .config import Settings
from .docling_parser import parse_document
from .extraction_service import extract_fields
from .field_mapper import map_fields
from .models import ProcessingResult
from .validation_service import validate_fields

logger = logging.getLogger(__name__)


def process_document(file_bytes: bytes, filename: str) -> ProcessingResult:
    logger.info("Document processing started: source=%r", filename)
    stage = "konfiguráció"
    try:
        settings = Settings.from_env()
        stage = "Docling feldolgozás"
        parsed = parse_document(file_bytes, filename, settings=settings)
        stage = "LLM mezőkinyerés"
        extraction = extract_fields(parsed, settings)
        stage = "séma betöltés"
        columns = schema_service.load_schema()[settings.target_table]
        descriptions = schema_service.load_descriptions().get(settings.target_table, {}).get("columns", {})
        stage = "mezőmegfeleltetés"
        mapping = map_fields(extraction, columns, descriptions, settings)
        stage = "validáció"
        issues = validate_fields(mapping, columns)
        return ProcessingResult(parsed_document=parsed, extraction=extraction,
                                mapping=mapping, validation_issues=issues)
    except Exception as exc:
        # Log stack locations without potentially sensitive exception messages.
        logger.error("Document stage failed: stage=%s error=%s stack=%s", stage,
                     type(exc).__name__, traceback.extract_tb(exc.__traceback__).format())
        if isinstance(exc, AppError):
            raise
        raise AppError(f"A dokumentum elemzése sikertelen ({stage}). Ellenőrizd a beállításokat.") from exc
