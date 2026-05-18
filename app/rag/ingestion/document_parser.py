from io import BytesIO
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def normalize_text(text: str) -> str:
    """Whitespace tisztítás úgy, hogy a bekezdések olvashatók maradjanak."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned = []
    previous_blank = False

    for line in lines:
        if not line:
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue

        cleaned.append(line)
        previous_blank = False

    return "\n".join(cleaned).strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PDF szöveg kinyerése pypdf segítségével."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "A PDF feltöltéshez hiányzik a pypdf csomag. Futtasd: pip install -r requirements.txt"
        ) from exc

    reader = PdfReader(BytesIO(file_bytes))
    page_texts = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_text(text)
        if text:
            page_texts.append(f"Page {page_number}\n{text}")

    return "\n\n".join(page_texts).strip()


def extract_text_from_txt(file_bytes: bytes) -> str:
    """TXT fájl dekódolása UTF-8 elsőbbséggel, Windows fallbackkel."""
    for encoding in ("utf-8", "utf-8-sig", "cp1250", "latin-1"):
        try:
            return normalize_text(file_bytes.decode(encoding))
        except UnicodeDecodeError:
            continue

    return normalize_text(file_bytes.decode("utf-8", errors="ignore"))


def extract_text_from_upload(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """Feltöltött PDF/TXT fájlból nyers szöveget és dokumentumtípust ad vissza."""
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(file_bytes), "pdf"

    if suffix == ".txt":
        return extract_text_from_txt(file_bytes), "txt"

    raise ValueError(f"Nem támogatott fájltípus: {suffix or 'ismeretlen'}")
