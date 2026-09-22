import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from standx_sdk.domain.orders import OrdersApi
from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.models.market import InstrumentRules
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


def _rules() -> InstrumentRules:
    return InstrumentRules(
        symbol="BTC-USD",
        base_asset="BTC",
        base_decimals=9,
        quote_asset="DUSD",
        quote_decimals=9,
        price_tick_decimals=2,
        qty_tick_decimals=4,
        min_order_qty=Decimal("0.0001"),
        max_order_qty=Decimal(100),
        max_position_size=Decimal(10),
        max_leverage=20,
        def_leverage=10,
        max_open_orders=100,
        price_cap_ratio=Decimal("0.3"),
        price_floor_ratio=Decimal("0.3"),
        maker_fee=Decimal("0.0001"),
        taker_fee=Decimal("0.0004"),
        depth_ticks=(Decimal("0.01"),),
    )


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
    assert result.cl_ord_id is not None
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
            "cl_ord_id": result.cl_ord_id,
        },
    }


def test_new_order_generates_client_order_id_when_omitted() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "message": "success", "request_id": "r1"})

    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(handler),
            request_signer=FakeSigner(),
        )
    )

    asyncio.run(
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

    body = seen["body"]
    assert isinstance(body, dict)
    assert isinstance(body["cl_ord_id"], str)
    assert body["cl_ord_id"]


def test_order_creation_can_fetch_rules_before_local_validation() -> None:
    calls: list[str] = []

    async def rules_provider(symbol: str) -> InstrumentRules:
        calls.append(symbol)
        return _rules()

    transport = HttpTransport(
        "https://perps.standx.com",
        httpx.MockTransport(lambda _: httpx.Response(200, json={"code": 0})),
        request_signer=FakeSigner(),
    )
    api = OrdersApi(transport, rules_provider=rules_provider)

    with pytest.raises(StandXError) as caught:
        asyncio.run(
            api.create(
                CreateOrderRequest(
                    symbol="BTC-USD",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    qty=Decimal("0.00001"),
                    price=Decimal(50000),
                    time_in_force=TimeInForce.GTC,
                    reduce_only=False,
                )
            )
        )

    assert caught.value.code is ErrorCode.VALIDATION_ERROR
    assert calls == ["BTC-USD"]


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


def test_new_order_timeout_maps_to_unknown_order_state() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(handler),
            request_signer=FakeSigner(),
        )
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(
            api.create(
                CreateOrderRequest(
                    symbol="BTC-USD",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    qty=Decimal("0.1"),
                    price=Decimal(50000),
                    time_in_force=TimeInForce.GTC,
                    reduce_only=False,
                    cl_ord_id="client-timeout",
                )
            )
        )

    assert caught.value.code is ErrorCode.ORDER_UNKNOWN
    assert caught.value.retryable is False
    assert "query" in caught.value.message


@pytest.mark.parametrize("method", ["cancel", "cancel_many"])
def test_cancel_timeout_maps_to_unknown_order_state(method: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(handler),
            request_signer=FakeSigner(),
        )
    )

    with pytest.raises(StandXError) as caught:
        if method == "cancel":
            asyncio.run(api.cancel(cl_ord_id="client-timeout"))
        else:
            asyncio.run(api.cancel_many(cl_ord_ids=["client-timeout"]))

    assert caught.value.code is ErrorCode.ORDER_UNKNOWN
    assert caught.value.retryable is False
    assert "query" in caught.value.message


def test_new_order_malformed_success_response_is_protocol_error() -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(lambda _: httpx.Response(200, json={"message": "success"})),
            request_signer=FakeSigner(),
        )
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(
            api.create(
                CreateOrderRequest(
                    symbol="BTC-USD",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    qty=Decimal("0.1"),
                    time_in_force=TimeInForce.GTC,
                    reduce_only=False,
                )
            )
        )

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


@pytest.mark.parametrize("path", ["/api/query_orders", "/api/query_open_orders"])
def test_order_list_malformed_success_response_is_protocol_error(path: str) -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
        )
    )

    with pytest.raises(StandXError) as caught:
        if path.endswith("open_orders"):
            asyncio.run(api.query_open_orders())
        else:
            asyncio.run(api.query_orders())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_order_submission_invalid_field_types_are_protocol_error() -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"code": "0", "message": "success", "request_id": "r"}
                )
            ),
            request_signer=FakeSigner(),
        )
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(
            api.create(
                CreateOrderRequest(
                    symbol="BTC-USD",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    qty=Decimal("0.1"),
                    time_in_force=TimeInForce.GTC,
                    reduce_only=False,
                )
            )
        )

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


def test_query_order_invalid_decimal_is_protocol_error() -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "id": 1,
                        "symbol": "BTC-USD",
                        "qty": "invalid",
                        "fill_qty": "0",
                        "fill_avg_price": "0",
                        "status": "open",
                        "time_in_force": "gtc",
                        "reduce_only": False,
                    },
                )
            ),
        )
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(api.query_order(order_id=1))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


@pytest.mark.parametrize("reduce_only", ["false", 1])
def test_query_order_rejects_non_boolean_reduce_only(reduce_only: object) -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "id": 1,
                        "symbol": "BTC-USD",
                        "qty": "1",
                        "fill_qty": "0",
                        "fill_avg_price": "0",
                        "status": "open",
                        "time_in_force": "gtc",
                        "reduce_only": reduce_only,
                    },
                )
            ),
        )
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(api.query_order(order_id=1))

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False


def test_query_orders_malformed_result_is_protocol_error() -> None:
    api = OrdersApi(
        HttpTransport(
            "https://perps.standx.com",
            httpx.MockTransport(
                lambda _: httpx.Response(200, json={"result": [{"id": 1}]})
            ),
        )
    )

    with pytest.raises(StandXError) as caught:
        asyncio.run(api.query_orders())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.retryable is False
