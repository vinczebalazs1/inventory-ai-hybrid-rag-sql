import os
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
from app.errors import LLMUnavailableError

load_dotenv()

client = None

MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")


def _get_client() -> OpenAI:
    """Create the OpenAI client lazily so the UI can start without a key."""
    global client

    if client is not None:
        return client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailableError(
            "Az AI keresési rész még nincs beállítva. Add meg az OPENAI_API_KEY értéket a .env fájlban, majd indítsd újra az alkalmazást.",
            detail="Missing environment variable: OPENAI_API_KEY",
        )

    client = OpenAI(api_key=api_key)
    return client


def embed_text(text: str) -> list[float]:
    """
    Convert text into embedding vector.
    """
    try:
        response = _get_client().embeddings.create(
            model=MODEL,
            input=text
        )
        return response.data[0].embedding
    except LLMUnavailableError:
        raise
    except OpenAIError as exc:
        raise LLMUnavailableError(
            "Az AI keresési rész most nem elérhető. Ellenőrizd az API kulcsot, a hozzáférést/billinget és a hálózati kapcsolatot, majd próbáld újra.",
            detail=str(exc),
        ) from exc
