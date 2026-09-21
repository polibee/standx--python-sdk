import asyncio
import json
from decimal import Decimal

import httpx

from standx_sdk.domain.orders import OrdersApi
from standx_sdk.models.order import CreateOrderRequest, OrderSide, OrderType, TimeInForce
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


def test_new_order_uses_documented_path_and_decimal_strings() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "r1"})

    transport = HttpTransport(
        "https://perps.standx.com", httpx.MockTransport(handler), request_signer=FakeSigner()
    )
    api = OrdersApi(transport)
    result = asyncio.run(
        api.create(
            CreateOrderRequest(
                symbol="BTC-USD",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                qty=Decimal("0.1"),
                price=Decimal(50000),
                time_in_force=TimeInForce.GTC,
                reduce_only=False,
            )
        )
    )

    assert result.request_id == "r1"
    assert seen == {
        "method": "POST",
        "path": "/api/new_order",
        "body": {
            "symbol": "BTC-USD",
            "side": "buy",
            "order_type": "limit",
            "qty": "0.1",
            "price": "50000",
            "time_in_force": "gtc",
            "reduce_only": False,
        },
    }


def test_cancel_requires_order_id_or_client_order_id() -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(lambda _: httpx.Response(200)),
            request_signer=FakeSigner(),
        )
    )

    try:
        asyncio.run(api.cancel())
    except ValueError as exc:
        assert "order_id" in str(exc) or "cl_ord_id" in str(exc)
    else:
        raise AssertionError("cancel without an identifier must fail locally")


def test_cancel_uses_documented_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "r2"})

    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com", httpx.MockTransport(handler), request_signer=FakeSigner()
        )
    )
    result = asyncio.run(api.cancel(cl_ord_id="client-1"))

    assert result.request_id == "r2"
    assert seen == {"path": "/api/cancel_order", "body": {"cl_ord_id": "client-1"}}
