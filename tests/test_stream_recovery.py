import asyncio
from decimal import Decimal

from standx_sdk.domain.order_recovery import OrderStateReconciler
from standx_sdk.models.order import Order
from standx_sdk.models.stream import BalanceEvent, PositionEvent, PriceEvent, UserOrderEvent
from standx_sdk.streams.market import MarketStream
from standx_sdk.streams.order_response import OrderResponseStream
from standx_sdk.testing.fake_websocket import FakeWebSocketServer


class FlakyTransport:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.connect_count = 0
        self.sent: list[str] = []

    async def connect(self) -> None:
        self.connect_count += 1
        if self.connect_count <= self.failures:
            raise ConnectionError("offline")

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def receive(self) -> str:
        return "{}"

    async def close(self) -> None:
        return None


def test_market_stream_retries_with_exponential_backoff() -> None:
    transport = FlakyTransport(failures=2)
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]
    delays: list[float] = []

    async def scenario() -> None:
        await stream.connect_with_backoff(
            max_attempts=3,
            initial_delay=0.25,
            sleep=lambda delay: delays.append(delay),
        )

    asyncio.run(scenario())

    assert transport.connect_count == 3
    assert delays == [0.25, 0.5]


def test_market_user_channels_map_to_typed_events() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    order = stream.decode({"channel": "order", "data": {"id": 1, "status": "filled", "qty": "1.0"}})
    position = stream.decode({"channel": "position", "data": {"id": 2, "qty": "0.5", "leverage": "10"}})
    balance = stream.decode({"channel": "balance", "data": {"token": "DUSD", "total": "100.0"}})

    assert isinstance(order, UserOrderEvent)
    assert order.status == "filled"
    assert isinstance(position, PositionEvent)
    assert position.qty == Decimal("0.5")
    assert isinstance(balance, BalanceEvent)
    assert balance.total == Decimal("100.0")


def test_market_price_event_maps_documented_last_price() -> None:
    stream = MarketStream("wss://example.test/ws-stream/v1")
    price = stream.decode(
        {
            "channel": "price",
            "data": {
                "symbol": "BTC-USD",
                "last_price": "121897.95",
                "mark_price": "121897.56",
            },
        }
    )
    assert isinstance(price, PriceEvent)
    assert price.last_price == Decimal("121897.95")
    assert price.mark_price == Decimal("121897.56")


def test_pending_order_response_can_be_recovered_from_rest() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="s")
    stream.request("order:new", {"cl_ord_id": "client-1"}, request_id="request-1")

    async def query(cl_ord_id: str) -> dict[str, object]:
        assert cl_ord_id == "client-1"
        return {"cl_ord_id": cl_ord_id, "status": "filled"}

    recovered = asyncio.run(stream.recover_pending(query))

    assert recovered == [{"cl_ord_id": "client-1", "status": "filled"}]
    assert stream.pending_request_ids == set()


def test_order_state_reconciler_uses_rest_snapshot_for_user_order_event() -> None:
    order = Order(
        id=7,
        cl_ord_id="client-1",
        symbol="BTC-USD",
        side="buy",
        order_type="limit",
        qty=Decimal(1),
        fill_qty=Decimal(1),
        fill_avg_price=Decimal(50000),
        status="filled",
        time_in_force="gtc",
        reduce_only=False,
    )
    calls: list[str] = []

    async def query(cl_ord_id: str) -> Order | None:
        calls.append(cl_ord_id)
        return order

    reconciler = OrderStateReconciler(query)
    event = UserOrderEvent(
        id=7,
        status="filled",
        qty=Decimal(1),
        cl_ord_id="client-1",
    )

    result = asyncio.run(reconciler.apply_user_event(event))

    assert result is order
    assert reconciler.get("client-1") is order
    assert calls == ["client-1"]


def test_order_state_reconciler_keeps_unknown_user_event_out_of_cache() -> None:
    async def query(_: str) -> Order | None:
        return None

    reconciler = OrderStateReconciler(query)
    event = UserOrderEvent(id=7, status="filled", qty=Decimal(1))

    assert asyncio.run(reconciler.apply_user_event(event)) is None
    assert reconciler.get(None) is None


def test_order_response_recovery_keeps_pending_when_rest_has_no_snapshot() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="s")
    stream.request("order:new", {"cl_ord_id": "client-1"}, request_id="request-1")

    async def query(_: str) -> Order | None:
        return None

    reconciler = OrderStateReconciler(query)

    recovered = asyncio.run(reconciler.recover_pending(stream))

    assert recovered == []
    assert stream.pending_request_ids == {"request-1"}


def test_fake_websocket_server_round_trips_stream_messages() -> None:
    server = FakeWebSocketServer()
    stream = MarketStream(
        "wss://example.test/ws-stream/v1",
        transport=server.transport,
    )

    async def scenario() -> dict[str, object]:
        await stream.connect()
        await stream.subscribe("price", "BTC-USD")
        return await server.receive_from_client()

    message = asyncio.run(scenario())
    assert message == {
        "subscribe": {"channel": "price", "symbol": "BTC-USD"},
    }


def test_order_response_reconnect_does_not_resend_pending_side_effect() -> None:
    class FlakyOrderTransport(FlakyTransport):
        pass

    transport = FlakyOrderTransport(failures=0)
    stream = OrderResponseStream(
        "wss://example.test/ws-api/v1", session_id="s", transport=transport  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        await stream.connect()
        await stream.send_request(
            "order:new", {"cl_ord_id": "client-1"}, request_id="request-1"
        )
        await stream.reconnect()

    asyncio.run(scenario())

    assert stream.pending_request_ids == {"request-1"}
    assert len(transport.sent) == 1


def test_order_response_stream_retries_connection_with_exponential_backoff() -> None:
    transport = FlakyTransport(failures=2)
    stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1", session_id="s", transport=transport  # type: ignore[arg-type]
    )
    delays: list[float] = []

    async def scenario() -> None:
        await stream.connect_with_backoff(
            max_attempts=3,
            initial_delay=0.25,
            sleep=lambda delay: delays.append(delay),
        )

    asyncio.run(scenario())

    assert transport.connect_count == 3
    assert delays == [0.25, 0.5]
