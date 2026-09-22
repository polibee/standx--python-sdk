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
from standx_sdk.models.trade import FundingPayment, FundingRate, UserTrade
from standx_sdk.resilience.rate_limit import CreditRateLimiter
from standx_sdk.resilience.retry import RetryPolicy
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


def test_http_transport_rejects_expired_token_before_network_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(handler),
        token="jwt",
    )
    transport.set_token_expiry(1)

    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/api/query_balance"))

    assert caught.value.code is ErrorCode.TOKEN_EXPIRED
    assert caught.value.retryable is False
    assert calls == 0


def test_replacing_token_clears_previous_expiry_metadata() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
        token="jwt",
    )
    transport.set_token_expiry(1)
    transport.set_token("opaque-token")

    assert asyncio.run(transport.get("/api/query_balance")) == {"ok": True}


def test_http_transport_retries_get_only_when_policy_is_explicitly_provided() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"message": "slow"})
        return httpx.Response(200, json={"ok": True})

    async def sleep(delay: float) -> None:
        assert delay == 0

    transport = HttpTransport("https://perps.standx.com", httpx.MockTransport(handler))
    result = asyncio.run(
        transport.get("/api/query_balance", retry_policy=RetryPolicy(sleep=sleep))
    )

    assert result == {"ok": True}
    assert calls == 2


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
            return httpx.Response(200, json={"balance": "10.5", "equity": "11.0", "upnl": "0.5"})
        if request.url.path == "/api/query_positions":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[])

    api = AccountApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))

    async def collect() -> tuple[BalanceSnapshot, list[PositionSnapshot]]:
        return await asyncio.gather(api.balance(), api.positions())

    balance, positions = asyncio.run(collect())

    assert balance.balance == Decimal("10.5")
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


@pytest.mark.parametrize("leverage", [True, 1.5, 0, -1])
def test_change_leverage_rejects_non_positive_integer_before_network(leverage: object) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    api = AccountApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(handler),
            request_signer=FakeSigner(),
        )
    )
    with pytest.raises(ValueError):
        asyncio.run(api.change_leverage("BTC-USD", leverage))  # type: ignore[arg-type]
    assert calls == 0


def test_position_config_field_types_are_protocol_errors() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"symbol": 1, "leverage": True, "margin_mode": "cross"},
            )
        ),
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(AccountApi(transport).position_config("BTC-USD"))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


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
                        "bankruptcy_price": "109608.01",
                        "created_at": "2025-08-10T09:05:50.265265Z",
                        "id": 15,
                        "symbol": "BTC-USD",
                        "qty": "0.5",
                        "entry_price": "50000",
                        "entry_value": "25000",
                        "holding_margin": "2500",
                        "initial_margin": "2500",
                        "leverage": "10",
                        "liq_price": "112373.50",
                        "maint_margin": "625",
                        "margin_asset": "DUSD",
                        "margin_mode": "isolated",
                        "mark_price": "49900",
                        "mmr": "0.025",
                        "position_value": "24950",
                        "realized_pnl": "31.61532",
                        "status": "open",
                        "time": "2025-08-11T03:41:40.922818Z",
                        "updated_at": "2025-08-10T09:05:50.265265Z",
                        "upnl": "-50",
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
    assert positions[0].bankruptcy_price == Decimal("109608.01")
    assert positions[0].holding_margin == Decimal(2500)
    assert positions[0].liq_price == Decimal("112373.50")
    assert positions[0].mmr == Decimal("0.025")
    assert positions[0].margin_asset == "DUSD"
    assert positions[0].time == "2025-08-11T03:41:40.922818Z"


def test_orders_api_queries_typed_order_snapshots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query_order"
        assert request.url.params["cl_ord_id"] == "client-1"
        return httpx.Response(
            200,
            json={
                "id": 101,
                "cl_ord_id": "client-1",
                "avail_locked": "3.0",
                "closed_block": -1,
                "created_at": "2025-08-11T03:35:25.559151Z",
                "created_block": -1,
                "symbol": "BTC-USD",
                "side": "buy",
                "order_type": "limit",
                "qty": "0.1",
                "fill_qty": "0",
                "fill_avg_price": "0",
                "liq_id": 0,
                "margin": "10",
                "price": "50000",
                "position_id": 15,
                "remark": "",
                "status": "open",
                "source": "user",
                "time_in_force": "gtc",
                "reduce_only": False,
                "user": "bsc_0x...",
            },
        )

    api = OrdersApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))
    order = asyncio.run(api.query_order(cl_ord_id="client-1"))

    assert isinstance(order, Order)
    assert order.id == 101
    assert order.qty == Decimal("0.1")
    assert order.avail_locked == Decimal("3.0")
    assert order.margin == Decimal(10)
    assert order.position_id == 15
    assert order.source == "user"
    assert order.created_at == "2025-08-11T03:35:25.559151Z"


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


def test_account_history_queries_send_documented_filters_and_pagination() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=[])

    api = AccountApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))

    async def collect() -> None:
        await api.trades(
            "BTC-USD",
            last_id=10,
            side="sell",
            start="2025-08-11T00:00:00Z",
            end="2025-08-12T00:00:00Z",
            limit=50,
        )
        await api.funding_history(
            "BTC-USD",
            start="2025-08-11T00:00:00Z",
            end="2025-08-12T00:00:00Z",
            last_id=20,
            limit=25,
        )

    asyncio.run(collect())

    assert seen == [
        (
            "/api/query_trades",
            {
                "symbol": "BTC-USD",
                "last_id": "10",
                "side": "sell",
                "start": "2025-08-11T00:00:00Z",
                "end": "2025-08-12T00:00:00Z",
                "limit": "50",
            },
        ),
        (
            "/api/query_funding_history",
            {
                "symbol": "BTC-USD",
                "start": "2025-08-11T00:00:00Z",
                "end": "2025-08-12T00:00:00Z",
                "last_id": "20",
                "limit": "25",
            },
        ),
    ]


def test_account_api_maps_documented_funding_rate_snapshots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query_funding_rates"
        assert request.url.params["symbol"] == "BTC-USD"
        assert request.url.params["start_time"] == "1000"
        assert request.url.params["end_time"] == "2000"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "symbol": "BTC-USD",
                    "funding_rate": "0.0001",
                    "index_price": "121601.158461",
                    "mark_price": "121602.43",
                    "premium": "0.0001",
                    "time": "2025-08-11T03:48:47.086505Z",
                    "created_at": "2025-08-11T03:48:47.086505Z",
                    "updated_at": "2025-08-11T03:48:47.086505Z",
                }
            ],
        )

    api = AccountApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))
    rates = asyncio.run(api.funding_rate_snapshots("BTC-USD", 1000, 2000))

    assert rates == [
        FundingRate(
            id=1,
            symbol="BTC-USD",
            funding_rate=Decimal("0.0001"),
            index_price=Decimal("121601.158461"),
            mark_price=Decimal("121602.43"),
            premium=Decimal("0.0001"),
            time="2025-08-11T03:48:47.086505Z",
            created_at="2025-08-11T03:48:47.086505Z",
            updated_at="2025-08-11T03:48:47.086505Z",
        )
    ]


def test_account_balance_malformed_success_response_is_protocol_error() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"balance": "10", "equity": "10"}
            )
        ),
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(AccountApi(transport).balance())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_account_balance_non_finite_decimal_is_protocol_error() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "balance": "NaN",
                    "available": "10",
                    "frozen": "0",
                    "equity": "10",
                },
            )
        ),
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(AccountApi(transport).balance())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_account_position_invalid_decimal_is_protocol_error() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "result": [
                        {"id": 1, "symbol": "BTC-USD", "qty": "invalid", "leverage": 10}
                    ]
                },
            )
        ),
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(AccountApi(transport).positions())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    "method, payload",
    [
        (
            "positions",
            {"result": [{"id": True, "symbol": "BTC-USD", "qty": "1", "leverage": 10}]},
        ),
        (
            "trades",
            {
                "result": [
                    {
                        "id": 1,
                        "order_id": 2,
                        "symbol": 3,
                        "side": "buy",
                        "price": "1",
                        "qty": "1",
                        "value": "1",
                        "fee_asset": "DUSD",
                        "fee_qty": "0",
                        "pnl": "0",
                    }
                ]
            },
        ),
        (
            "funding_history",
            {
                "result": [
                    {
                        "id": 1,
                        "asset": "DUSD",
                        "symbol": "BTC-USD",
                        "qty": "1",
                        "txn_type": "funding",
                        "transact_time": 1,
                    }
                ]
            },
        ),
    ],
)
def test_account_snapshot_field_types_are_protocol_errors(
    method: str, payload: dict[str, object]
) -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    api = AccountApi(transport)

    with pytest.raises(StandXError) as caught:
        if method == "positions":
            asyncio.run(api.positions())
        elif method == "trades":
            asyncio.run(api.trades())
        else:
            asyncio.run(api.funding_history())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_account_funding_history_malformed_success_response_is_protocol_error() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"result": [{"id": 1, "asset": "DUSD"}]}
            )
        ),
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(AccountApi(transport).funding_history())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    "method",
    ["positions", "trades", "funding_history", "funding_rates"],
)
def test_account_list_malformed_success_response_is_protocol_error(method: str) -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(lambda _: httpx.Response(200, json={"unexpected": []})),
    )
    api = AccountApi(transport)

    with pytest.raises(StandXError) as caught:
        if method == "positions":
            asyncio.run(api.positions())
        elif method == "trades":
            asyncio.run(api.trades())
        elif method == "funding_history":
            asyncio.run(api.funding_history())
        else:
            asyncio.run(api.funding_rates("BTC-USD", 1, 2))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


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


def test_invalid_retry_after_header_does_not_escape_rate_limit_mapping() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "not-a-number"},
            json={"code": 429, "message": "slow down"},
        )

    transport = HttpTransport("https://perps.standx.com", httpx.MockTransport(handler))
    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/api/query_balance"))

    assert caught.value.code is ErrorCode.RATE_LIMITED
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds is None


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


def test_http_transport_maps_successful_invalid_json_to_protocol_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    transport = HttpTransport("https://perps.standx.com", httpx.MockTransport(handler))

    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/api/query_balance"))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_http_transport_maps_connection_error_to_retryable_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    transport = HttpTransport("https://perps.standx.com", httpx.MockTransport(handler))

    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/api/query_balance"))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
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


def test_closed_http_transport_returns_stable_protocol_error() -> None:
    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True})),
    )
    asyncio.run(transport.aclose())

    with pytest.raises(StandXError) as caught:
        asyncio.run(transport.get("/closed"))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_http_transport_close_is_idempotent() -> None:
    transport = HttpTransport("https://perps.standx.com")

    async def close_twice() -> None:
        await transport.aclose()
        await transport.aclose()

    asyncio.run(close_twice())
