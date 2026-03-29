import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PayloadSchemaType

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION = os.getenv("QDRANT_COLLECTION", "devices")
FILTER_INDEX_FIELDS = {
    "name": PayloadSchemaType.KEYWORD,
}

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)


def ensure_filter_indexes():
    """
    Ensure payload indexes exist for fields used in filters.
    """
    collection_info = client.get_collection(collection_name=COLLECTION)
    payload_schema = collection_info.payload_schema or {}

    for field_name, schema in FILTER_INDEX_FIELDS.items():
        if field_name not in payload_schema:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field_name,
                field_schema=schema
            )


def init_collection():
    """
    Create collection only if it does not exist.
    """
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION not in existing:
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
    Insert or update vectors.
    """
    client.upsert(
        collection_name=COLLECTION,
        points=points
    )


def search(vector: list, query_filter=None, limit: int = 3):
    """
    Search similar vectors.
    """
    if query_filter is not None:
        ensure_filter_indexes()

    response = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=query_filter,
        limit=limit
    )
    return response.points
