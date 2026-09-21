import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from standx_sdk.domain.account import AccountApi
from standx_sdk.domain.orders import OrdersApi
from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.models.account import BalanceSnapshot, PositionSnapshot
from standx_sdk.models.order import MarginMode, Order
from standx_sdk.models.trade import FundingPayment, UserTrade
from standx_sdk.resilience.rate_limit import CreditRateLimiter
from standx_sdk.transport.http import HttpTransport


class FakeSigner:
    def sign_request(
        self, version: str, request_id: str, timestamp: int, payload: str
    ) -> dict[str, str]:
        return {
            "x-request-sign-version": version,
            "x-request-id": request_id,
            "x-request-timestamp": str(timestamp),
            "x-request-signature": "signature",
        }


def test_authenticated_transport_adds_bearer_impersonate_and_session_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({key.lower(): value for key, value in request.headers.items()})
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "r"})

    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(handler),
        token="jwt",
        impersonate="cv_1",
        session_id="session-1",
    )
    asyncio.run(transport.post("/api/change_leverage", json={"symbol": "BTC-USD", "leverage": 10}))

    assert seen["authorization"] == "Bearer jwt"
    assert seen["x-impersonate"] == "cv_1"
    assert seen["x-session-id"] == "session-1"


def test_signed_post_adds_standx_request_signature_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({key.lower(): value for key, value in request.headers.items()})
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "r"})

    class FakeSigner:
        def sign_request(
            self, version: str, request_id: str, timestamp: int, payload: str
        ) -> dict[str, str]:
            assert version == "v1"
            assert '"leverage":10' in payload
            return {
                "x-request-sign-version": version,
                "x-request-id": request_id,
                "x-request-timestamp": str(timestamp),
                "x-request-signature": "signature",
            }

    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(handler),
        request_signer=FakeSigner(),
    )
    asyncio.run(
        transport.post(
            "/api/change_leverage", json={"symbol": "BTC-USD", "leverage": 10}, signed=True
        )
    )

    assert seen["x-request-sign-version"] == "v1"
    assert seen["x-request-signature"] == "signature"


def test_bulk_cancel_uses_one_documented_identifier_list() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "bulk"})

    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com", httpx.MockTransport(handler), request_signer=FakeSigner()
        )
    )
    result = asyncio.run(api.cancel_many(cl_ord_ids=["a", "b"]))

    assert result.request_id == "bulk"
    assert seen == {"path": "/api/cancel_orders", "body": {"cl_ord_id_list": ["a", "b"]}}


def test_account_api_maps_balance_and_position_endpoints() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/query_balance":
            return httpx.Response(200, json={"balance": "10.5", "equity": "11.0"})
        if request.url.path == "/api/query_positions":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[])

    api = AccountApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))

    async def collect() -> tuple[dict[str, object], list[dict[str, object]]]:
        return await asyncio.gather(api.balance(), api.positions())

    balance, positions = asyncio.run(collect())

    assert balance["balance"] == Decimal("10.5")
    assert positions == []
    assert paths == ["/api/query_balance", "/api/query_positions"]


def test_account_api_maps_position_config_and_margin_changes() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"symbol": "BTC-USD", "leverage": 10, "margin_mode": "cross"})
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "r"})

    api = AccountApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(handler),
            request_signer=FakeSigner(),
        )
    )
    config, leverage, margin = asyncio.run(
        _collect_position_config(api)
    )

    assert config.symbol == "BTC-USD"
    assert config.leverage == 10
    assert config.margin_mode is MarginMode.CROSS
    assert leverage.request_id == "r"
    assert margin.request_id == "r"
    assert seen == [
        {"symbol": "BTC-USD", "leverage": 15},
        {"symbol": "BTC-USD", "margin_mode": "isolated"},
    ]


async def _collect_position_config(api: AccountApi) -> tuple[object, object, object]:
    return await asyncio.gather(
        api.position_config_snapshot("BTC-USD"),
        api.change_leverage_config("BTC-USD", 15),
        api.change_margin_mode_config("BTC-USD", MarginMode.ISOLATED),
    )


def test_account_api_returns_documented_typed_snapshots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/query_balance":
            return httpx.Response(
                200,
                json={
                    "balance": "10.5",
                    "equity": "11.0",
                    "upnl": "0.5",
                    "cross_available": "9.0",
                },
            )
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "id": 15,
                        "symbol": "BTC-USD",
                        "qty": "0.5",
                        "entry_price": "50000",
                        "leverage": "10",
                        "margin_mode": "isolated",
                        "status": "open",
                    }
                ]
            },
        )

    api = AccountApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))

    async def collect() -> tuple[BalanceSnapshot, list[PositionSnapshot]]:
        return await asyncio.gather(api.balance_snapshot(), api.position_snapshots())

    balance, positions = asyncio.run(collect())

    assert isinstance(balance, BalanceSnapshot)
    assert balance.balance == Decimal("10.5")
    assert isinstance(positions[0], PositionSnapshot)
    assert positions[0].qty == Decimal("0.5")


def test_orders_api_queries_typed_order_snapshots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query_order"
        assert request.url.params["cl_ord_id"] == "client-1"
        return httpx.Response(
            200,
            json={
                "id": 101,
                "cl_ord_id": "client-1",
                "symbol": "BTC-USD",
                "side": "buy",
                "order_type": "limit",
                "qty": "0.1",
                "fill_qty": "0",
                "fill_avg_price": "0",
                "price": "50000",
                "status": "open",
                "time_in_force": "gtc",
                "reduce_only": False,
            },
        )

    api = OrdersApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))
    order = asyncio.run(api.query_order(cl_ord_id="client-1"))

    assert isinstance(order, Order)
    assert order.id == 101
    assert order.qty == Decimal("0.1")


def test_account_api_maps_user_trades_and_funding_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/query_trades":
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": 7,
                            "order_id": 101,
                            "symbol": "BTC-USD",
                            "side": "sell",
                            "price": "50000",
                            "qty": "0.1",
                            "value": "5000",
                            "fee_asset": "DUSD",
                            "fee_qty": "2",
                            "pnl": "1",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "id": 8,
                    "asset": "DUSD",
                    "symbol": "BTC-USD",
                    "qty": "-0.1",
                    "txn_type": "funding",
                    "transact_time": "2026-01-01T00:00:00Z",
                }
            ],
        )

    api = AccountApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))
    trades, funding = asyncio.run(
        _collect_trade_history(api)
    )
    assert isinstance(trades[0], UserTrade)
    assert trades[0].fee_qty == Decimal(2)
    assert isinstance(funding[0], FundingPayment)
    assert funding[0].qty == Decimal("-0.1")


async def _collect_trade_history(api: AccountApi) -> tuple[list[UserTrade], list[FundingPayment]]:
    return await asyncio.gather(api.trade_snapshots("BTC-USD"), api.funding_history("BTC-USD"))


def test_rate_limit_response_maps_to_retryable_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, headers={"retry-after": "2"}, json={"code": 429, "message": "slow down"}
        )

    transport = HttpTransport("https://perps.standx.com", httpx.MockTransport(handler))
    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/api/query_balance"))

    assert caught.value.code is ErrorCode.RATE_LIMITED
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds == 2.0


def test_http_transport_maps_auth_and_validation_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("validation"):
            return httpx.Response(
                400,
                headers={"x-request-id": "req-400"},
                json={"message": "invalid qty"},
            )
        return httpx.Response(401, json={"message": "token expired"})

    transport = HttpTransport("https://perps.standx.com", httpx.MockTransport(handler))
    with pytest.raises(StandXError) as validation:
        asyncio.run(transport.get("/validation"))
    with pytest.raises(StandXError) as auth:
        asyncio.run(transport.get("/auth"))

    assert validation.value.code is ErrorCode.VALIDATION_ERROR
    assert validation.value.request_id == "req-400"
    assert validation.value.message == "invalid qty"
    assert auth.value.code is ErrorCode.AUTH_FAILED
    assert auth.value.message == "token expired"


def test_http_transport_maps_network_timeout_and_uses_configured_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = HttpTransport(
        "https://perps.standx.com", httpx.MockTransport(handler), timeout_seconds=2.5
    )
    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/slow"))

    assert transport.timeout_seconds == 2.5
    assert caught.value.code is ErrorCode.REQUEST_TIMEOUT
    assert caught.value.retryable is True


def test_http_transport_acquires_credit_before_each_request() -> None:
    now = [0.0]
    limiter = CreditRateLimiter(clock=lambda: now[0], sleep=asyncio.sleep)
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={"ok": True})

    transport = HttpTransport(
        "https://perps.standx.com", httpx.MockTransport(handler), rate_limiter=limiter
    )
    asyncio.run(transport.get("/one"))
    asyncio.run(transport.get("/two"))

    assert requests == 2
    assert limiter.available_credits == 810
