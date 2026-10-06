"""Sanitized operational errors; never include source records or secrets."""


class ExtractError(Exception):
    def __init__(
        self,
        code: str,
        message: str = "Operation failed",
        exit_code: int = 4,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}
