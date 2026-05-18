"""
Alkalmazásszintű hibák, amelyek biztonságosan megjeleníthetők a UI-ban.
"""


class AppError(Exception):
    """Alap hibatípus felhasználói üzenettel és opcionális hibakeresési részlettel."""

    def __init__(
        self,
        message: str,
        *,
        title: str = "Something needs attention",
        code: str = "APP_ERROR",
        detail: str | None = None,
    ):
        super().__init__(message)
        self.title = title
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict:
        # A frontend ezt a stabil struktúrát várja, amikor az orchestrator ok=False választ ad.
        return {
            "code": self.code,
            "title": self.title,
            "message": str(self),
            "detail": self.detail,
        }


class LLMUnavailableError(AppError):
    """Akkor dobjuk, ha az LLM konfigurációs vagy API hiba miatt nem használható."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(
            message,
            title="Az AI szolgáltatás nem elérhető",
            code="LLM_UNAVAILABLE",
            detail=detail,
        )


class DatabaseUnavailableError(AppError):
    """Akkor dobjuk, ha az adatbázis nem érhető el vagy nincs jól konfigurálva."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(
            message,
            title="Az adatbázis nem elérhető",
            code="DATABASE_UNAVAILABLE",
            detail=detail,
        )


class UserInputError(AppError):
    """Akkor dobjuk, ha a felhasználói input nem dolgozható fel biztonságosan."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(
            message,
            title="Kérlek fogalmazd át a kérdést",
            code="USER_INPUT_ERROR",
            detail=detail,
        )
