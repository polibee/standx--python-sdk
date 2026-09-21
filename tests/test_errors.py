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
