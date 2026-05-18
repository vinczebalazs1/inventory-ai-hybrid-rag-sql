from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.rag.embedding.embedding_service import embed_text
from app.rag.ingestion.chunker import chunk_all_devices, chunk_document_text
from app.rag.ingestion.document_parser import extract_text_from_upload
from app.rag.ingestion.parser import parse_devices
from app.rag.vector_store.qdrant_client import init_collection, upsert_points


def _point_id(chunk, index: int) -> str:
    source = chunk.source or chunk.name
    raw_id = f"{chunk.doc_type}:{source}:{chunk.section}:{index}:{chunk.text[:80]}"
    return str(uuid5(NAMESPACE_URL, raw_id))


def upsert_chunks(chunks: list) -> int:
    """
    Chunk lista embeddingelése és feltöltése Qdrantba.
    """

    init_collection()

    points = []

    for i, chunk in enumerate(chunks):
        vector = embed_text(chunk.text)

        points.append({
            "id": _point_id(chunk, i),
            "vector": vector,
            "payload": {
                "name": chunk.name,
                "section": chunk.section,
                "text": chunk.text,
                "source": chunk.source or chunk.name,
                "doc_type": chunk.doc_type,
            }
        })

    if points:
        upsert_points(points)

    return len(points)


def ingest_devices(path: str) -> int:
    """
    Teljes ingestion feldolgozási lánc:
    TXT -> parse -> chunk -> embed -> Qdrant
    """

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    devices = parse_devices(text)
    chunks = chunk_all_devices(devices)

    for chunk in chunks:
        chunk.source = Path(path).name
        chunk.doc_type = "device_txt"

    print(f"Chunks: {len(chunks)}")
    inserted = upsert_chunks(chunks)

    print("Ingestion complete")
    return inserted


def ingest_uploaded_document(filename: str, file_bytes: bytes) -> int:
    """
    Felhasználó által feltöltött PDF/TXT dokumentum feldolgozása és Qdrantba írása.
    """

    text, doc_type = extract_text_from_upload(filename, file_bytes)
    if not text:
        raise ValueError("A feltöltött dokumentumból nem sikerült szöveget kinyerni.")

    chunks = chunk_document_text(
        text,
        source=Path(filename).name,
        doc_type=doc_type,
    )

    if not chunks:
        raise ValueError("A feltöltött dokumentumból nem készült kereshető chunk.")

    return upsert_chunks(chunks)
