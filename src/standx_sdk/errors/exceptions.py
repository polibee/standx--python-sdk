from .codes import ErrorCode


class StandXError(Exception):
    """Base exception carrying a stable SDK error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        request_id: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retryable = retryable
        self.retry_after_seconds: float | None = None
