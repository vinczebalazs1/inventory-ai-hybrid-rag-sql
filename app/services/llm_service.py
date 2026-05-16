"""
Thin wrapper around the OpenAI client for text generation tasks.

The helper function centralizes model invocation parameters so all services can
reuse a single call pattern.
"""

import os
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
from app.errors import LLMUnavailableError

# Load API credentials and related runtime configuration.
load_dotenv()

client = None


def _get_client() -> OpenAI:
    """Create the OpenAI client lazily so the UI can start without a key."""
    global client

    if client is not None:
        return client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailableError(
            "Az AI rész még nincs beállítva. Add meg az OPENAI_API_KEY értéket a .env fájlban, majd indítsd újra az alkalmazást.",
            detail="Missing environment variable: OPENAI_API_KEY",
        )

    client = OpenAI(api_key=api_key)
    return client


def ask_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Send a single user prompt to the selected model and return text content.

    Parameters:
    - prompt: full prompt string to send as a user message.
    - model: model identifier, defaults to a lightweight general-purpose model.
    """
    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            # Use deterministic output for stable SQL and answer generation.
            temperature=0
        )
        return response.choices[0].message.content or ""
    except LLMUnavailableError:
        raise
    except OpenAIError as exc:
        raise LLMUnavailableError(
            "Az AI szolgáltatás most nem tud válaszolni. Ellenőrizd az API kulcsot, a hozzáférést/billinget és a hálózati kapcsolatot, majd próbáld újra.",
            detail=str(exc),
        ) from exc
