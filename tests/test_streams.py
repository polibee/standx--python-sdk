from standx_sdk.models.stream import OrderResponseEvent
from standx_sdk.streams.market import MarketStream
from standx_sdk.streams.order_response import OrderResponseStream


class FakeTransport:
    def __init__(self) -> None:
        self.connect_count = 0
        self.close_count = 0
        self.sent: list[str] = []

    async def connect(self) -> None:
        self.connect_count += 1

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def receive(self) -> str:
        return "{}"

    async def close(self) -> None:
        self.close_count += 1


class AuthFakeTransport(FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.incoming = ['{"channel":"auth","data":{"code":200,"msg":"success"}}']

    async def receive(self) -> str:
        return self.incoming.pop(0)


def test_market_stream_builds_documented_subscription_envelope() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    assert stream.subscription("depth_book", "BTC-USD") == {
        "subscribe": {"channel": "depth_book", "symbol": "BTC-USD"}
    }


def test_market_stream_reconnects_and_replays_subscriptions() -> None:
    transport = FakeTransport()
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]

    import asyncio

    async def scenario() -> None:
        await stream.connect()
        await stream.subscribe("price", "BTC-USD")
        await stream.reconnect()

    asyncio.run(scenario())

    assert transport.connect_count == 2
    assert len(transport.sent) == 2
    assert '"channel":"price"' in transport.sent[-1]


def test_closed_market_stream_does_not_reconnect() -> None:
    transport = FakeTransport()
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]

    import asyncio

    async def scenario() -> None:
        await stream.close_async()
        try:
            await stream.reconnect()
        except RuntimeError as error:
            assert "closed" in str(error)
        else:
            raise AssertionError("closed stream must not reconnect")

    asyncio.run(scenario())


def test_market_stream_authenticates_before_user_subscription() -> None:
    transport = AuthFakeTransport()
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]

    import asyncio

    async def scenario() -> None:
        await stream.connect()
        await stream.authenticate("jwt-token", impersonate="cv_1")
        await stream.subscribe("order")

    asyncio.run(scenario())

    assert transport.sent[0] == '{"auth":{"token":"jwt-token","impersonate":"cv_1"}}'
    assert transport.sent[1] == '{"subscribe":{"channel":"order"}}'


def test_market_stream_rejects_user_subscription_before_authentication() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=FakeTransport())  # type: ignore[arg-type]

    import asyncio

    async def scenario() -> None:
        try:
            await stream.subscribe("balance")
        except RuntimeError as error:
            assert "authenticate" in str(error)
        else:
            raise AssertionError("user subscriptions require authentication")

    asyncio.run(scenario())


def test_order_response_stream_builds_documented_request_envelope() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    message = stream.request("order:new", {"qty": "0.1"}, request_id="request-1")

    assert message["session_id"] == "session-1"
    assert message["request_id"] == "request-1"
    assert message["method"] == "order:new"
    assert message["params"] == '{"qty":"0.1"}'


def test_order_response_stream_tracks_request_ids_until_response() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    stream.request("order:new", {"qty": "0.1"}, request_id="request-1")

    assert stream.pending_request_ids == {"request-1"}
    assert stream.resolve({"request_id": "request-1", "code": 0}) == {
        "request_id": "request-1",
        "code": 0,
    }
    assert stream.pending_request_ids == set()


def test_order_response_stream_classifies_documented_response_states() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    accepted = stream.decode_response(
        {"code": 0, "status": "accepted", "request_id": "request-1"}
    )
    rejected = stream.decode_response(
        {"code": 400, "message": "alo order rejected", "request_id": "request-2"}
    )

    assert isinstance(accepted, OrderResponseEvent)
    assert accepted.state == "accepted"
    assert rejected.state == "rejected"
    assert rejected.message == "alo order rejected"
