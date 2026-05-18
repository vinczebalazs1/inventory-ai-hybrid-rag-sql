from typing import List, Dict
from app.rag.models.rag_models import RagChunk


def chunk_device(device: Dict) -> List[RagChunk]:
    """
    Parse-olt eszköz átalakítása chunk objektumokká.

    Bemenet:
    {
        "name": "printer",
        "sections": {
            "description": "...",
            "usage": "...",
            ...
        }
    }

    Kimenet:
    [
        RagChunk(name="printer", section="usage", text="..."),
        ...
    ]
    """

    name = device["name"]
    sections = device.get("sections", {})

    chunks = []

    for section_name, content in sections.items():
        content = content.strip()

        if not content:
            # Üres szekciókból nem készül vektor, mert csak szennyeznék
            # a visszakeresési eredményeket.
            continue

        # A jelenlegi chunkolás szekció-alapú: egy dokumentációs szekcióból
        # egy RagChunk lesz. Token-méret szerinti darabolás még nincs.
        chunks.append(
            RagChunk(
                name=name,
                section=section_name,
                text=content
            )
        )

    return chunks


def chunk_all_devices(devices: List[Dict]) -> List[RagChunk]:
    """
    Az összes parse-olt eszköz feldolgozása egy lapos chunk listába.
    """

    all_chunks = []

    for device in devices:
        # Az összes eszköz chunkjait egy lapos listába gyűjtjük ingestionhöz.
        device_chunks = chunk_device(device)
        all_chunks.extend(device_chunks)

    return all_chunks


def chunk_document_text(
    text: str,
    *,
    source: str,
    doc_type: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> List[RagChunk]:
    """
    Általános PDF/TXT dokumentum darabolása RAG chunkokra.
    """

    text = text.strip()
    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError("Az overlap kisebb kell legyen, mint a chunk_size.")

    chunks = []
    start = 0
    index = 1

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            paragraph_break = text.rfind("\n\n", start, end)
            sentence_break = text.rfind(". ", start, end)
            break_at = max(paragraph_break, sentence_break)

            if break_at > start + (chunk_size // 2):
                end = break_at + 1

        content = text[start:end].strip()
        if content:
            chunks.append(
                RagChunk(
                    name=source.lower(),
                    section=f"chunk-{index}",
                    text=content,
                    source=source,
                    doc_type=doc_type,
                )
            )
            index += 1

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks
