import asyncio

import httpx
import pytest

from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.transport.http import HttpTransport


def test_expired_token_runs_recovery_before_get() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"ok": True})

    transport = HttpTransport(
        "https://paper.example",
        httpx.MockTransport(handler),
        token="old-token",
    )
    transport.set_token_expiry(0)

    async def recover() -> str:
        transport.set_token("new-token")
        return "new-token"

    transport.set_auth_recovery(recover)

    assert asyncio.run(transport.get("/health")) == {"ok": True}
    assert seen == ["Bearer new-token"]


def test_get_401_runs_recovery_once_without_replaying_post_mutations() -> None:
    get_calls = 0
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_calls, post_calls
        if request.method == "GET":
            get_calls += 1
            return (
                httpx.Response(401, json={"message": "expired"})
                if get_calls == 1
                else httpx.Response(200, json={"ok": True})
            )
        post_calls += 1
        return httpx.Response(401, json={"message": "expired"})

    transport = HttpTransport("https://paper.example", httpx.MockTransport(handler))
    recoveries = 0

    async def recover() -> str:
        nonlocal recoveries
        recoveries += 1
        return "new-token"

    transport.set_auth_recovery(recover)

    assert asyncio.run(transport.get("/health")) == {"ok": True}
    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.post("/order", json={"symbol": "BTC-USD"}))

    assert get_calls == 2
    assert post_calls == 1
    assert recoveries == 1
    assert caught.value.code is ErrorCode.AUTH_FAILED
