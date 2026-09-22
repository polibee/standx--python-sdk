import socket
import ssl
from collections.abc import Iterator

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
        transport_error_type: str | None = None,
        transport_error_types: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retryable = retryable
        self.server_code = server_code
        self.retry_after_seconds: float | None = None
        self.transport_error_type = transport_error_type
        self.transport_error_types = transport_error_types

    @classmethod
    def from_transport(
        cls,
        code: ErrorCode,
        message: str,
        exception: BaseException,
        *,
        request_id: str | None = None,
        retryable: bool = False,
        server_code: int | str | None = None,
    ) -> "StandXError":
        error_type, error_types = classify_transport_error(exception)
        return cls(
            code=code,
            message=f"{message} ({error_type})",
            request_id=request_id,
            retryable=retryable,
            server_code=server_code,
            transport_error_type=error_type,
            transport_error_types=error_types,
        )


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


def classify_transport_error(exception: BaseException) -> tuple[str, tuple[str, ...]]:
    """Return safe transport diagnostics without exposing exception details."""

    types = tuple(type(item).__name__ for item in _exception_chain(exception))
    chain = tuple(_exception_chain(exception))
    if any(isinstance(item, ssl.SSLError) for item in chain):
        return "TLS error", types
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "DNS error", types
    if "ConnectTimeout" in types:
        return "ConnectTimeout", types
    if "ReadTimeout" in types:
        return "ReadTimeout", types
    if "WriteTimeout" in types:
        return "WriteTimeout", types
    if "PoolTimeout" in types:
        return "PoolTimeout", types
    if "TimeoutError" in types:
        return "TimeoutError", types
    if any(
        name.startswith("ConnectionClosed")
        or name in {"ConnectionResetError", "BrokenPipeError", "EOFError", "RemoteProtocolError"}
        for name in types
    ):
        return "RemoteDisconnect", types
    if "ProxyError" in types:
        return "ProxyError", types
    if "ConnectError" in types:
        return "ConnectError", types
    if "ReadError" in types:
        return "ReadError", types
    return types[0] if types else "TransportError", types


def _exception_chain(exception: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exception
    for _ in range(8):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__
