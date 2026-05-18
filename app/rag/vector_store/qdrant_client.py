import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PayloadSchemaType

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION = os.getenv("QDRANT_COLLECTION", "devices")
FILTER_INDEX_FIELDS = {
    # A HYBRID visszakeresés a payload.name mező alapján szűri a dokumentációs chunkokat,
    # ezért ezen a mezőn index kell a hatékony szűrt kereséshez.
    "name": PayloadSchemaType.KEYWORD,
}

# A Qdrant kliens process-szintű globális objektum. Ettől egyszerű a használat,
# de productionben jobb lehet a késleltetett létrehozás és explicit health check.
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)


def ensure_filter_indexes():
    """
    Biztosítja, hogy a szűréshez használt mezőkön legyen payload index.
    """
    collection_info = client.get_collection(collection_name=COLLECTION)
    payload_schema = collection_info.payload_schema or {}

    # Csak a hiányzó indexeket hozzuk létre. A meglévő payload indexek újrakészítése
    # felesleges, és Qdrant beállítástól függően hibázhat is.
    for field_name, schema in FILTER_INDEX_FIELDS.items():
        if field_name not in payload_schema:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field_name,
                field_schema=schema
            )


def init_collection():
    """
    Collection létrehozása csak akkor, ha még nem létezik.
    """
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION not in existing:
        # A vektorméretnek egyeznie kell az embedding modellel.
        # A text-embedding-3-large alapból 3072 dimenziós vektort ad vissza.
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=3072,
                distance=Distance.COSINE
            )
        )

    ensure_filter_indexes()


def upsert_points(points: list):
    """
    Vektorok beszúrása vagy frissítése.
    """
    # Minden pontnak id, vector és payload mezőt kell tartalmaznia.
    # Az ingestion service ezt a formát RagChunk objektumokból építi.
    client.upsert(
        collection_name=COLLECTION,
        points=points
    )


def search(vector: list, query_filter=None, limit: int = 3):
    """
    Hasonló vektorok keresése.
    """
    if query_filter is not None:
        # A szűrt HYBRID keresések a name payload indexre támaszkodnak.
        ensure_filter_indexes()

    response = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=query_filter,
        limit=limit
    )
    return response.points
