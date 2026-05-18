import os
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
from app.errors import LLMUnavailableError

load_dotenv()

client = None

MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")


def _get_client() -> OpenAI:
    """OpenAI kliens késleltetett létrehozása, hogy a UI kulcs nélkül is el tudjon indulni."""
    global client

    # Az első létrehozás után újrahasználjuk az embeddings klienst.
    # Embedding hívás ingestionkor és futásidejű visszakereséskor is történik.
    if client is not None:
        return client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # A RAG embedding nélkül nem tud működni, ezért a hiányzó API kulcsot
        # AI elérhetőségi/konfigurációs problémaként jelezzük.
        raise LLMUnavailableError(
            "Az AI keresési rész még nincs beállítva. Add meg az OPENAI_API_KEY értéket a .env fájlban, majd indítsd újra az alkalmazást.",
            detail="Missing environment variable: OPENAI_API_KEY",
        )

    client = OpenAI(api_key=api_key)
    return client


def embed_text(text: str) -> list[float]:
    """
    Szöveg átalakítása embedding vektorrá.
    """
    try:
        # A visszakapott vektornak ugyanakkora dimenziójúnak kell lennie,
        # mint a Qdrant collection. text-embedding-3-large esetén ez várhatóan 3072.
        response = _get_client().embeddings.create(
            model=MODEL,
            input=text
        )
        return response.data[0].embedding
    except LLMUnavailableError:
        raise
    except OpenAIError as exc:
        # A provider-specifikus részleteket kivesszük a normál UI-ból,
        # de hibakeresési módhoz megőrizzük őket.
        raise LLMUnavailableError(
            "Az AI keresési rész most nem elérhető. Ellenőrizd az API kulcsot, a hozzáférést/billinget és a hálózati kapcsolatot, majd próbáld újra.",
            detail=str(exc),
        ) from exc
