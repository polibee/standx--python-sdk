import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from standx_sdk.domain.account import AccountApi
from standx_sdk.domain.orders import OrdersApi
from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.models.account import BalanceSnapshot, PositionSnapshot
from standx_sdk.models.order import Order
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
