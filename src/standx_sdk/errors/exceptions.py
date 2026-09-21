from .codes import ErrorCode


class StandXError(Exception):
    """Base exception carrying a stable SDK error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        request_id: str | None = None,
        retryable: bool = False,
        server_code: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retryable = retryable
        self.server_code = server_code
        self.retry_after_seconds: float | None = None


class OrderValidationError(StandXError):
    """A local order check failed against documented symbol rules."""

    def __init__(self, field: str, value: object, rule: str) -> None:
        self.field = field
        self.value = str(value)
        self.rule = rule
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"{field}={value} violates {rule}",
            retryable=False,
        )
