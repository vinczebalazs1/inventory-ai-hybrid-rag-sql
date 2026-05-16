"""
Application-level errors that are safe to show in the UI.
"""


class AppError(Exception):
    """Base error with a user-facing message and optional debug detail."""

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
        return {
            "code": self.code,
            "title": self.title,
            "message": str(self),
            "detail": self.detail,
        }


class LLMUnavailableError(AppError):
    """Raised when the LLM cannot be used because of config or API problems."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(
            message,
            title="Az AI szolgáltatás nem elérhető",
            code="LLM_UNAVAILABLE",
            detail=detail,
        )


class DatabaseUnavailableError(AppError):
    """Raised when the database cannot be reached or configured."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(
            message,
            title="Az adatbázis nem elérhető",
            code="DATABASE_UNAVAILABLE",
            detail=detail,
        )


class UserInputError(AppError):
    """Raised when the user input cannot be processed safely."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(
            message,
            title="Kérlek fogalmazd át a kérdést",
            code="USER_INPUT_ERROR",
            detail=detail,
        )
