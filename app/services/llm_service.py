"""
Vékony wrapper az OpenAI kliens körül szöveggenerálási feladatokhoz.

A helper függvény központosítja a modellhívás paramétereit, így minden service
ugyanazt a hívási mintát tudja újrahasználni.
"""

import os
from openai import APIConnectionError, APITimeoutError, OpenAI, OpenAIError
from dotenv import load_dotenv
from app.errors import LLMUnavailableError

# API hitelesítési adatok és kapcsolódó futásidejű konfiguráció betöltése.
load_dotenv()

client = None


def _provider_error(exc: OpenAIError) -> LLMUnavailableError:
    """Classify failures without exposing provider bodies, prompts or credentials."""
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    parameter = getattr(exc, "param", None)
    billing_codes = {
        "insufficient_quota", "credit_balance_exhausted", "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded", "organization_usage_limit_exceeded",
    }
    safe_codes = billing_codes | {"unsupported_value", "unsupported_parameter", "model_not_found",
                                 "invalid_api_key", "rate_limit_exceeded", "slow_down", "server_is_overloaded"}
    safe_parameters = {"temperature", "top_p", "model", "reasoning_effort", "max_tokens",
                       "max_completion_tokens", "messages", "response_format", "tools"}
    code = code if isinstance(code, str) and code in safe_codes else None
    parameter = parameter if isinstance(parameter, str) and parameter in safe_parameters else None
    if isinstance(exc, APITimeoutError):
        message = "Az AI-kérés időtúllépés miatt megszakadt. Próbáld újra később."
    elif isinstance(exc, APIConnectionError):
        message = "Nem sikerült kapcsolódni az AI szolgáltatáshoz. Ellenőrizd a hálózatot, proxyt és a TLS-beállításokat."
    elif status == 401:
        message = "Az AI API elutasította a hitelesítést (401). Ellenőrizd az alkalmazás által használt API-kulcsot és a hozzáférési beállításokat."
    elif status == 403:
        message = "Az AI API megtagadta a hozzáférést (403). Ellenőrizd a projekt és a modell jogosultságait."
    elif status == 404:
        message = "A kért AI-modell vagy erőforrás nem érhető el (404). Ellenőrizd a modell nevét és a projekt hozzáférését."
    elif status == 429 and code in billing_codes:
        message = "Az AI API keret- vagy számlázási korlátot jelzett (429). Ellenőrizd az API-projekt és a szervezet kreditjeit, illetve limitjeit."
    elif status == 429:
        message = "Az AI API hívási sebességkorlátot jelzett (429). Várj, majd próbáld újra."
    elif status == 400:
        field = f" ({parameter})" if parameter else ""
        message = f"Az AI API hibás vagy nem támogatott kérési paramétert jelzett{field} (400). A modellhez tartozó hívásbeállításokat kell ellenőrizni."
    elif isinstance(status, int) and status >= 500:
        message = "Az AI szolgáltatás átmeneti szerverhibát jelzett. Próbáld újra később."
    else:
        message = "Az AI-kérés nem teljesült. Az ellenőrzött hibakategória a technikai részletekben látható."
    detail = f"exception={type(exc).__name__}; http_status={status}; code={code}; parameter={parameter}"
    return LLMUnavailableError(message, detail=detail)


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


def ask_llm(prompt: str, model: str = "gpt-6-luna") -> str:
    """
    Egyetlen felhasználói prompt elküldése a kiválasztott modellnek, majd a szöveg visszaadása.

    Paraméterek:
    - prompt: teljes prompt string, amely felhasználói üzenetként megy a modellnek.
    - model: modellazonosító; alapból könnyű általános célú modell.
    """
    try:
        # A modell alapparamétereit használjuk. A GPT-6 alapértelmezett reasoning
        # módja nem támogatja a korábban minden kérésre küldött temperature=0-t.
        response = _get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
    except LLMUnavailableError:
        # A saját barátságos hibánkat változtatás nélkül továbbengedjük.
        raise
    except OpenAIError as exc:
        # A nyers providerüzenet az exception-láncon keresztül se kerüljön a UI-ba.
        raise _provider_error(exc) from None
