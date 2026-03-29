from app.rag.ingestion.parser import parse_devices
from app.rag.ingestion.chunker import chunk_all_devices
from app.rag.embedding.embedding_service import embed_text
from app.rag.vector_store.qdrant_client import init_collection, upsert_points


def ingest_devices(path: str):
    """
    Full ingestion pipeline:
    TXT → parse → chunk → embed → Qdrant
    """

    # 🔹 1. load file
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # 🔹 2. parse
    devices = parse_devices(text)

    # 🔹 3. chunk
    chunks = chunk_all_devices(devices)

    print(f"Chunks: {len(chunks)}")

    # 🔹 4. init collection
    init_collection()

    # 🔹 5. build points
    points = []

    for i, chunk in enumerate(chunks):
        vector = embed_text(chunk.text)

        points.append({
            "id": i,
            "vector": vector,
            "payload": {
                "name": chunk.name,
                "section": chunk.section,
                "text": chunk.text
            }
        })

    # 🔹 6. upload
    upsert_points(points)

    print("✅ Ingestion complete")