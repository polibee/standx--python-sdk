import socket
import ssl

import httpx

from standx_sdk.errors import ErrorCode, StandXError


def test_error_keeps_code_request_id_and_retryability() -> None:
    error = StandXError(
        code=ErrorCode.RATE_LIMITED,
        message="rate limited",
        request_id="request-1",
        retryable=True,
        server_code="E_RATE_LIMIT",
    )

    assert error.code is ErrorCode.RATE_LIMITED
    assert error.request_id == "request-1"
    assert error.retryable is True
    assert error.server_code == "E_RATE_LIMIT"


def test_transport_error_records_connect_timeout_type() -> None:
    error = StandXError.from_transport(
        ErrorCode.REQUEST_TIMEOUT,
        "HTTP request timed out",
        httpx.ConnectTimeout("connect timed out"),
        retryable=True,
    )

    assert error.transport_error_type == "ConnectTimeout"
    assert error.transport_error_types == ("ConnectTimeout",)


def test_transport_error_classifies_tls_and_dns_causes_without_raw_details() -> None:
    tls_exception = httpx.ConnectError("connection failed")
    tls_exception.__cause__ = ssl.SSLError("private detail")
    dns_exception = httpx.ConnectError("connection failed")
    dns_exception.__cause__ = socket.gaierror("private detail")
    tls = StandXError.from_transport(
        ErrorCode.PROTOCOL_ERROR,
        "HTTP connection failed",
        tls_exception,
        retryable=True,
    )
    dns = StandXError.from_transport(
        ErrorCode.PROTOCOL_ERROR,
        "HTTP connection failed",
        dns_exception,
        retryable=True,
    )

    assert tls.transport_error_type == "TLS error"
    assert tls.transport_error_types == ("ConnectError", "SSLError")
    assert dns.transport_error_type == "DNS error"
    assert dns.transport_error_types == ("ConnectError", "gaierror")
    assert "private detail" not in tls.message
    assert "private detail" not in dns.message


def test_transport_error_classifies_proxy_failures() -> None:
    error = StandXError.from_transport(
        ErrorCode.PROTOCOL_ERROR,
        "HTTP connection failed",
        httpx.ProxyError("private proxy detail"),
        retryable=True,
    )

    assert error.transport_error_type == "ProxyError"
    assert error.transport_error_types == ("ProxyError",)
    assert "private proxy detail" not in error.message
