"""
Vékony wrapper az OpenAI kliens körül szöveggenerálási feladatokhoz.

A helper függvény központosítja a modellhívás paramétereit, így minden service
ugyanazt a hívási mintát tudja újrahasználni.
"""

import os
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
from app.errors import LLMUnavailableError

# API hitelesítési adatok és kapcsolódó futásidejű konfiguráció betöltése.
load_dotenv()

client = None


def _get_client() -> OpenAI:
    """OpenAI kliens késleltetett létrehozása, hogy a UI kulcs nélkül is el tudjon indulni."""
    global client

    # Az első sikeres létrehozás után újrahasználjuk ugyanazt az SDK klienst.
    # Így nem építjük újra a kliens objektumot minden requestnél.
    if client is not None:
        return client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # A hiányzó kulcs konfigurációs hiba, nem a felhasználó kérdésének hibája.
        raise LLMUnavailableError(
            "Az AI rész még nincs beállítva. Add meg az OPENAI_API_KEY értéket a .env fájlban, majd indítsd újra az alkalmazást.",
            detail="Missing environment variable: OPENAI_API_KEY",
        )

    client = OpenAI(api_key=api_key)
    return client


def ask_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Egyetlen felhasználói prompt elküldése a kiválasztott modellnek, majd a szöveg visszaadása.

    Paraméterek:
    - prompt: teljes prompt string, amely felhasználói üzenetként megy a modellnek.
    - model: modellazonosító; alapból könnyű általános célú modell.
    """
    try:
        # Minden chat-alapú LLM hívás ezen az egy függvényen megy át, így a model,
        # temperature és hibakezelés egységes marad a service-ek között.
        response = _get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            # Determinisztikus kimenet stabil SQL- és válaszgeneráláshoz.
            temperature=0
        )
        return response.choices[0].message.content or ""
    except LLMUnavailableError:
        # A saját barátságos hibánkat változtatás nélkül továbbengedjük.
        raise
    except OpenAIError as exc:
        # A provider-specifikus SDK hibákat olyan alkalmazáshibává alakítjuk,
        # amelyet az orchestrator/frontend meg tud jeleníteni.
        raise LLMUnavailableError(
            "Az AI szolgáltatás most nem tud válaszolni. Ellenőrizd az API kulcsot, a hozzáférést/billinget és a hálózati kapcsolatot, majd próbáld újra.",
            detail=str(exc),
        ) from exc
