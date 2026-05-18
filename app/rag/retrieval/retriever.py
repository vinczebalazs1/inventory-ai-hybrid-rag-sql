from typing import List, Dict
from app.rag.embedding.embedding_service import embed_text
from app.rag.vector_store.qdrant_client import search
from qdrant_client.models import Filter, FieldCondition, MatchValue


def _chunk_from_hit(hit) -> Dict:
    chunk = dict(hit.payload or {})
    chunk["score"] = getattr(hit, "score", None)
    return chunk


def retrieve_semantic(question: str, limit: int = 3) -> List[Dict]:
    """
    Tiszta szemantikai keresés RAG módban.
    """

    # A futásidejű RAG azzal indul, hogy a felhasználó kérdését ugyanabba a vektortérbe
    # ágyazzuk be, amelyet ingestionkor is használtunk.
    vector = embed_text(question)

    results = search(vector, limit=limit)

    # Keep payload fields and the Qdrant score so the UI can show confidence.
    chunks = [_chunk_from_hit(hit) for hit in results]

    return chunks


def retrieve_by_name(name: str, question: str, limit: int = 3) -> List[Dict]:
    """
    Szűrt keresés hybrid módhoz.
    """

    # Név szerinti szűrésnél is a kérdés embeddingjét használjuk arra,
    # hogy a találó eszköz chunkjait szemantikai relevancia szerint rendezzük.
    vector = embed_text(question)

    # Ez leszűkíti a vektorkeresést az SQL által megtalált item/eszköz chunkjaira.
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

    chunks = [_chunk_from_hit(hit) for hit in results]

    return chunks
