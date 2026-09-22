import asyncio
from decimal import Decimal

import httpx
import pytest

from standx_sdk.domain.markets import MarketsApi
from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.models.market import KlineResolution
from standx_sdk.transport.http import HttpTransport


def _api(handler):
    return MarketsApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))


def test_kline_history_maps_parallel_arrays_to_typed_bars() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/kline/history"
        assert dict(request.url.params) == {
            "symbol": "BTC-USD",
            "from": "100",
            "to": "200",
            "resolution": "5",
            "countback": "2",
        }
        return httpx.Response(
            200,
            json={
                "s": "ok",
                "t": [1754897028, 1754897031],
                "c": ["121897.95", "121903.04"],
                "o": ["121896.02", "121898.05"],
                "h": ["121897.95", "121903.15"],
                "l": ["121895.92", "121898.05"],
                "v": ["0.09", "10.542"],
            },
        )

    result = asyncio.run(
        _api(handler).kline_history(
            "BTC-USD", 100, 200, KlineResolution.FIVE_MINUTES, countback=2
        )
    )

    assert result.status == "ok"
    assert result.bars[0].time == 1754897028
    assert result.bars[0].close == Decimal("121897.95")
    assert result.bars[1].volume == Decimal("10.542")


def test_market_server_time_and_health_use_documented_wire_formats() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/kline/time":
            return httpx.Response(200, json=1620000000)
        return httpx.Response(200, text="OK")

    api = _api(handler)
    assert asyncio.run(api.server_time()) == 1620000000
    assert asyncio.run(api.health()) == "OK"


@pytest.mark.parametrize(
    "payload",
    [
        {"s": "error", "t": [], "c": [], "o": [], "h": [], "l": [], "v": []},
        {"s": "ok", "t": [1, 2], "c": [1], "o": [1, 2], "h": [1, 2], "l": [1, 2], "v": [1, 2]},
        {"s": "ok", "t": [1], "c": ["NaN"], "o": [1], "h": [1], "l": [1], "v": [1]},
    ],
)
def test_malformed_kline_response_is_protocol_error(payload: dict[str, object]) -> None:
    api = _api(lambda _: httpx.Response(200, json=payload))

    with pytest.raises(StandXError) as caught:
        asyncio.run(api.kline_history("BTC-USD", 1, 2, "1"))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    "args",
    [
        ("BTC-USD", 2, 1, "1"),
        ("BTC-USD", 1, 2, "30"),
        ("BTC-USD", 1, 2, "1", 0),
    ],
)
def test_kline_parameters_are_validated_before_network(args: tuple[object, ...]) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    api = _api(handler)
    with pytest.raises(ValueError):
        if len(args) == 5:
            asyncio.run(api.kline_history(*args[:4], countback=args[4]))
        else:
            asyncio.run(api.kline_history(*args))
    assert calls == 0
