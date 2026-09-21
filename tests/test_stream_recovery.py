import asyncio
from decimal import Decimal

import pytest

from standx_sdk.domain.order_recovery import OrderStateReconciler
from standx_sdk.errors import ErrorCode, StandXError
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

    order = stream.decode(
        {
            "channel": "order",
            "data": {
                "id": 1,
                "status": "filled",
                "qty": "1.0",
                "avail_locked": "3.0",
                "leverage": "15",
                "margin": "10.0",
                "position_id": 15,
                "source": "user",
                "user": "bsc_0x...",
            },
        }
    )
    position = stream.decode(
        {
            "channel": "position",
            "data": {
                "id": 2,
                "qty": "0.5",
                "leverage": "10",
                "created_at": "2025-08-10T09:05:50Z",
                "initial_margin": "100",
                "margin_asset": "DUSD",
                "realized_pnl": "2.5",
                "user": "bsc_0x...",
            },
        }
    )
    balance = stream.decode(
        {
            "channel": "balance",
            "data": {
                "token": "DUSD",
                "total": "100.0",
                "account_type": "perps",
                "id": "bsc_0x...",
                "is_enabled": True,
                "last_tx_updated_at": 0,
                "ref_id": 0,
                "version": 0,
                "wallet_id": "bsc_0x...",
            },
        }
    )

    assert isinstance(order, UserOrderEvent)
    assert order.status == "filled"
    assert order.avail_locked == Decimal("3.0")
    assert order.leverage == 15
    assert order.margin == Decimal("10.0")
    assert order.position_id == 15
    assert order.source == "user"
    assert isinstance(position, PositionEvent)
    assert position.qty == Decimal("0.5")
    assert position.initial_margin == Decimal(100)
    assert position.margin_asset == "DUSD"
    assert position.realized_pnl == Decimal("2.5")
    assert position.user == "bsc_0x..."
    assert isinstance(balance, BalanceEvent)
    assert balance.total == Decimal("100.0")
    assert balance.account_type == "perps"
    assert balance.is_enabled is True
    assert balance.wallet_id == "bsc_0x..."


def test_market_price_event_maps_documented_last_price() -> None:
    stream = MarketStream("wss://example.test/ws-stream/v1")
    price = stream.decode(
        {
            "channel": "price",
            "seq": 13,
            "data": {
                "symbol": "BTC-USD",
                "base": "BTC",
                "quote": "DUSD",
                "last_price": "121897.95",
                "mark_price": "121897.56",
                "time": "2025-08-11T07:23:50.923602474Z",
            },
        }
    )
    assert isinstance(price, PriceEvent)
    assert price.last_price == Decimal("121897.95")
    assert price.seq == 13
    assert price.mark_price == Decimal("121897.56")
    assert price.base == "BTC"
    assert price.quote == "DUSD"
    assert price.time == "2025-08-11T07:23:50.923602474Z"


def test_market_stream_rejects_non_integer_sequence_numbers() -> None:
    stream = MarketStream("wss://example.test/ws-stream/v1")

    with pytest.raises(StandXError) as caught:
        stream.decode(
            {
                "channel": "price",
                "seq": "13",
                "data": {"symbol": "BTC-USD", "last_price": "1"},
            }
        )

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


def test_pending_order_response_can_be_recovered_from_rest() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="s")
    stream.request(
        "order:new",
        {"cl_ord_id": "client-1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )

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


def test_order_state_reconciler_serializes_same_order_refreshes() -> None:
    active = 0
    max_active = 0

    async def query(cl_ord_id: str) -> Order:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return Order(
            id=7,
            cl_ord_id=cl_ord_id,
            symbol="BTC-USD",
            side="buy",
            order_type="limit",
            qty=Decimal(1),
            fill_qty=Decimal(0),
            fill_avg_price=Decimal(0),
            status="open",
            time_in_force="gtc",
            reduce_only=False,
        )

    reconciler = OrderStateReconciler(query)
    event = UserOrderEvent(id=7, status="open", qty=Decimal(1), cl_ord_id="client-1")

    async def scenario() -> None:
        await asyncio.gather(
            reconciler.apply_user_event(event),
            reconciler.apply_user_event(event),
        )

    asyncio.run(scenario())

    assert max_active == 1


def test_order_state_reconciler_keeps_different_order_refreshes_independent() -> None:
    active = 0
    max_active = 0

    async def query(cl_ord_id: str) -> Order:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return Order(
            id=1 if cl_ord_id == "client-1" else 2,
            cl_ord_id=cl_ord_id,
            symbol="BTC-USD",
            side="buy",
            order_type="limit",
            qty=Decimal(1),
            fill_qty=Decimal(0),
            fill_avg_price=Decimal(0),
            status="open",
            time_in_force="gtc",
            reduce_only=False,
        )

    reconciler = OrderStateReconciler(query)
    events = [
        UserOrderEvent(id=1, status="open", qty=Decimal(1), cl_ord_id="client-1"),
        UserOrderEvent(id=2, status="open", qty=Decimal(1), cl_ord_id="client-2"),
    ]

    async def scenario() -> None:
        await asyncio.gather(*(reconciler.apply_user_event(event) for event in events))

    asyncio.run(scenario())

    assert max_active == 2


def test_order_state_reconciler_keeps_unknown_user_event_out_of_cache() -> None:
    async def query(_: str) -> Order | None:
        return None

    reconciler = OrderStateReconciler(query)
    event = UserOrderEvent(id=7, status="filled", qty=Decimal(1))

    assert asyncio.run(reconciler.apply_user_event(event)) is None
    assert reconciler.get(None) is None


def test_order_response_recovery_keeps_pending_when_rest_has_no_snapshot() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="s")
    stream.request(
        "order:new",
        {"cl_ord_id": "client-1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )

    async def query(_: str) -> Order | None:
        return None

    reconciler = OrderStateReconciler(query)

    recovered = asyncio.run(reconciler.recover_pending(stream))

    assert recovered == []
    assert stream.pending_request_ids == {"request-1"}


def test_pending_recovery_shares_order_refresh_lock_with_user_events() -> None:
    active = 0
    max_active = 0
    order = Order(
        id=9,
        cl_ord_id="client-1",
        symbol="BTC-USD",
        side="buy",
        order_type="limit",
        qty=Decimal(1),
        fill_qty=Decimal(0),
        fill_avg_price=Decimal(0),
        status="open",
        time_in_force="gtc",
        reduce_only=False,
    )

    async def query(_: str) -> Order:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return order

    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="s")
    stream.request(
        "order:new",
        {"cl_ord_id": "client-1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )
    reconciler = OrderStateReconciler(query)
    event = UserOrderEvent(id=9, status="open", qty=Decimal(1), cl_ord_id="client-1")

    async def scenario() -> None:
        await asyncio.gather(
            reconciler.apply_user_event(event),
            reconciler.recover_pending(stream),
        )

    asyncio.run(scenario())

    assert max_active == 1
    assert reconciler.get("client-1") is order


def test_order_state_reconciler_restores_cache_from_open_orders() -> None:
    order = Order(
        id=8,
        cl_ord_id="client-2",
        symbol="BTC-USD",
        side="sell",
        order_type="limit",
        qty=Decimal(1),
        fill_qty=Decimal(0),
        fill_avg_price=Decimal(0),
        status="open",
        time_in_force="gtc",
        reduce_only=False,
    )
    reconciler = OrderStateReconciler(lambda _: _missing_order())

    async def query_open_orders() -> list[Order]:
        return [order]

    restored = asyncio.run(reconciler.restore_open_orders(query_open_orders))

    assert restored == [order]
    assert reconciler.get("client-2") is order


async def _missing_order() -> Order | None:
    return None


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
            "order:new",
            {"cl_ord_id": "client-1"},
            request_id="request-1",
            header={
                "x-request-id": "request-1",
                "x-request-timestamp": "1700000000000",
                "x-request-signature": "signature",
            },
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


def test_order_response_backoff_supports_max_delay_and_jitter() -> None:
    transport = FlakyTransport(failures=3)
    stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1", session_id="s", transport=transport  # type: ignore[arg-type]
    )
    delays: list[float] = []

    async def scenario() -> None:
        await stream.connect_with_backoff(
            max_attempts=4,
            initial_delay=1.0,
            max_delay=1.5,
            jitter=lambda delay: delay + 0.25,
            sleep=lambda delay: delays.append(delay),
        )

    asyncio.run(scenario())

    assert delays == [1.25, 1.5, 1.5]
