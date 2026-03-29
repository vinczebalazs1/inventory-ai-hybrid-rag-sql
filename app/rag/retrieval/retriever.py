from typing import List, Dict
from app.rag.embedding.embedding_service import embed_text
from app.rag.vector_store.qdrant_client import search
from qdrant_client.models import Filter, FieldCondition, MatchValue


def retrieve_semantic(question: str, limit: int = 3) -> List[Dict]:
    """
    Pure semantic search (RAG mode).
    """

    vector = embed_text(question)

    results = search(vector, limit=limit)

    chunks = [hit.payload for hit in results]

    return chunks


def retrieve_by_name(name: str, question: str, limit: int = 3) -> List[Dict]:
    """
    Filtered search for hybrid mode.
    """

    vector = embed_text(question)

    query_filter = Filter(
        must=[
            FieldCondition(
                key="name",
                match=MatchValue(value=name.lower())
            )
        ]
    )

    results = search(
        vector,
        query_filter=query_filter,
        limit=limit
    )

    chunks = [hit.payload for hit in results]

    return chunks