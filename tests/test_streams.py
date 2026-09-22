import asyncio

import pytest

from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.models.stream import OrderResponseEvent
from standx_sdk.streams.market import MarketStream
from standx_sdk.streams.order_response import OrderResponseStream
from standx_sdk.transport.websocket import WebSocketTransport


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


class SequenceAuthFakeTransport(FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.incoming = [
            '{"channel":"auth","data":{"code":200,"msg":"success"}}',
            '{"channel":"auth","data":{"code":401,"msg":"expired"}}',
        ]

    async def receive(self) -> str:
        return self.incoming.pop(0)


class RejectedAuthFakeTransport(FakeTransport):
    async def receive(self) -> str:
        return '{"channel":"auth","data":{"code":401,"msg":"expired"}}'


class MalformedAuthFakeTransport(FakeTransport):
    async def receive(self) -> str:
        return "not-json"


class WrongTypeAuthFakeTransport(FakeTransport):
    async def receive(self) -> str:
        return '{"channel":"auth","data":{"code":"200","msg":"success"}}'


class SubscriptionSendFailureTransport(FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_send = True

    async def send(self, message: str) -> None:
        if self.fail_next_send:
            self.fail_next_send = False
            raise ConnectionError("subscription send failed")
        await super().send(message)


class DisconnectedReceiveTransport(FakeTransport):
    async def receive(self) -> str:
        raise ConnectionError("socket disconnected")


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


def test_closed_market_stream_does_not_enter_connect_backoff() -> None:
    transport = FakeTransport()
    stream = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=transport  # type: ignore[arg-type]
    )
    delays: list[float] = []

    async def scenario() -> None:
        await stream.close_async()
        with pytest.raises(RuntimeError, match="closed"):
            await stream.connect_with_backoff(sleep=lambda delay: delays.append(delay))

    asyncio.run(scenario())

    assert transport.connect_count == 0
    assert delays == []


def test_closed_order_response_stream_does_not_enter_connect_backoff() -> None:
    transport = FakeTransport()
    stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1",
        session_id="session-1",
        transport=transport,  # type: ignore[arg-type]
    )
    delays: list[float] = []

    async def scenario() -> None:
        await stream.close_async()
        with pytest.raises(RuntimeError, match="closed"):
            await stream.connect_with_backoff(sleep=lambda delay: delays.append(delay))

    asyncio.run(scenario())

    assert transport.connect_count == 0
    assert delays == []


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


def test_market_stream_reconnect_replays_auth_streams() -> None:
    transport = AuthFakeTransport()
    transport.incoming.append('{"channel":"auth","data":{"code":200,"msg":"success"}}')
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]

    async def scenario() -> None:
        await stream.connect()
        await stream.authenticate("jwt-token", streams=["order", "trade"])
        await stream.reconnect()

    asyncio.run(scenario())

    assert transport.sent == [
        '{"auth":{"token":"jwt-token","streams":[{"channel":"order"},{"channel":"trade"}]}}',
        '{"auth":{"token":"jwt-token","streams":[{"channel":"order"},{"channel":"trade"}]}}',
    ]


def test_market_stream_reconnect_auth_failure_clears_authenticated_state() -> None:
    transport = SequenceAuthFakeTransport()
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]

    async def scenario() -> None:
        await stream.connect()
        await stream.authenticate("jwt-token")
        with pytest.raises(StandXError) as caught:
            await stream.reconnect()
        assert caught.value.code is ErrorCode.AUTH_FAILED

    asyncio.run(scenario())

    assert stream.authenticated is False


def test_market_stream_rejects_unsupported_auth_stream() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=FakeTransport())  # type: ignore[arg-type]

    async def scenario() -> None:
        with pytest.raises(ValueError, match="unsupported authenticated stream"):
            await stream.authenticate("jwt-token", streams=["price"])

    asyncio.run(scenario())


def test_market_stream_maps_rejected_authentication_to_auth_failed() -> None:
    stream = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=RejectedAuthFakeTransport()  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        with pytest.raises(StandXError) as caught:
            await stream.authenticate("jwt-token")
        assert caught.value.code is ErrorCode.AUTH_FAILED
        assert caught.value.server_code == 401

    asyncio.run(scenario())
    assert stream.authenticated is False


def test_market_stream_maps_malformed_authentication_to_protocol_error() -> None:
    stream = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=MalformedAuthFakeTransport()  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        with pytest.raises(StandXError) as caught:
            await stream.authenticate("jwt-token")
        assert caught.value.code is ErrorCode.PROTOCOL_ERROR

    asyncio.run(scenario())
    assert stream.authenticated is False


def test_market_stream_rejects_non_integer_auth_code_as_protocol_error() -> None:
    stream = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=WrongTypeAuthFakeTransport()  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        with pytest.raises(StandXError) as caught:
            await stream.authenticate("jwt-token")
        assert caught.value.code is ErrorCode.PROTOCOL_ERROR

    asyncio.run(scenario())
    assert stream.authenticated is False


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


def test_market_stream_wraps_subscription_restore_failure() -> None:
    class ResubscribeFailureTransport(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.reconnecting = False

        async def connect(self) -> None:
            self.connect_count += 1
            self.reconnecting = self.connect_count > 1

        async def send(self, message: str) -> None:
            if self.reconnecting:
                raise ConnectionError("subscription socket rejected")
            await super().send(message)

    transport = ResubscribeFailureTransport()
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1", transport=transport)  # type: ignore[arg-type]

    async def scenario() -> None:
        await stream.connect()
        await stream.subscribe("price", "BTC-USD")
        await stream.reconnect()

    with pytest.raises(StandXError) as caught:
        asyncio.run(scenario())

    assert caught.value.code is ErrorCode.WS_RESUBSCRIBE_FAILED
    assert "price:BTC-USD" in caught.value.message
    assert isinstance(caught.value.__cause__, StandXError)
    assert caught.value.__cause__.code is ErrorCode.WS_DISCONNECTED


def test_market_stream_does_not_record_subscription_until_send_succeeds() -> None:
    transport = SubscriptionSendFailureTransport()
    stream = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=transport  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        await stream.connect()
        with pytest.raises(StandXError) as caught:
            await stream.subscribe("price", "BTC-USD")
        assert caught.value.code is ErrorCode.WS_DISCONNECTED
        await stream.reconnect()

    asyncio.run(scenario())

    assert transport.sent == []


def test_order_response_stream_maps_send_disconnect_to_retryable_sdk_error() -> None:
    transport = SubscriptionSendFailureTransport()
    stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1",
        session_id="session-1",
        transport=transport,  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        await stream.connect()
        with pytest.raises(StandXError) as caught:
            await stream.send_request(
                "order:new",
                {"qty": "0.1"},
                request_id="request-1",
                header={
                    "x-request-id": "request-1",
                    "x-request-timestamp": "1700000000000",
                    "x-request-signature": "signature",
                },
            )
        assert caught.value.code is ErrorCode.WS_DISCONNECTED
        assert caught.value.retryable is True

    asyncio.run(scenario())


def test_websocket_transport_passes_ping_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_connect(endpoint: str, **kwargs: object) -> object:
        captured["endpoint"] = endpoint
        captured.update(kwargs)
        return object()

    import standx_sdk.transport.websocket as websocket_module

    monkeypatch.setattr(websocket_module.websockets, "connect", fake_connect)
    transport = WebSocketTransport(
        "wss://example.test/ws",
        ping_interval=20.0,
        ping_timeout=60.0,
    )

    asyncio.run(transport.connect())

    assert captured == {
        "endpoint": "wss://example.test/ws",
        "additional_headers": {},
        "ping_interval": 20.0,
        "ping_timeout": 60.0,
    }


def test_market_stream_maps_receive_disconnect_to_retryable_sdk_error() -> None:
    stream = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=DisconnectedReceiveTransport()  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        with pytest.raises(StandXError) as caught:
            await stream.receive()
        assert caught.value.code is ErrorCode.WS_DISCONNECTED
        assert caught.value.retryable is True

    asyncio.run(scenario())


def test_order_response_stream_maps_receive_disconnect_to_retryable_sdk_error() -> None:
    stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1",
        session_id="session-1",
        transport=DisconnectedReceiveTransport(),  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        with pytest.raises(StandXError) as caught:
            await stream.receive()
        assert caught.value.code is ErrorCode.WS_DISCONNECTED
        assert caught.value.retryable is True

    asyncio.run(scenario())


def test_order_response_stream_builds_documented_request_envelope() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    message = stream.request(
        "order:new",
        {"qty": "0.1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )

    assert message["session_id"] == "session-1"
    assert message["request_id"] == "request-1"
    assert message["method"] == "order:new"
    assert message["params"] == '{"qty":"0.1"}'


def test_order_response_stream_accepts_documented_authentication_header() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    message = stream.request(
        "order:new",
        {"qty": "0.1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )

    assert message["header"] == {
        "x-request-id": "request-1",
        "x-request-timestamp": "1700000000000",
        "x-request-signature": "signature",
    }


def test_order_response_stream_requires_authentication_header_for_orders() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    with pytest.raises(ValueError, match="authentication header"):
        stream.request("order:new", {"qty": "0.1"}, request_id="request-1")


def test_order_response_stream_requires_matching_non_empty_signature_headers() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    with pytest.raises(ValueError, match="x-request-id"):
        stream.request(
            "order:cancel",
            {"cl_ord_id": "client-1"},
            request_id="request-1",
            header={
                "x-request-id": "request-2",
                "x-request-timestamp": "1700000000000",
                "x-request-signature": "signature",
            },
        )

    with pytest.raises(ValueError, match="non-empty"):
        stream.request(
            "order:new",
            {"qty": "0.1"},
            request_id="request-1",
            header={
                "x-request-id": "request-1",
                "x-request-timestamp": "",
                "x-request-signature": "signature",
            },
        )


def test_order_response_stream_tracks_request_ids_until_response() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    stream.request(
        "order:new",
        {"qty": "0.1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )

    assert stream.pending_request_ids == {"request-1"}
    assert stream.resolve({"request_id": "request-1", "code": 0}) == {
        "request_id": "request-1",
        "code": 0,
    }
    assert stream.pending_request_ids == set()


def test_order_response_request_ids_must_be_non_empty_and_unique_while_pending() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")
    headers = {
        "x-request-id": "request-1",
        "x-request-timestamp": "1700000000000",
        "x-request-signature": "signature",
    }

    with pytest.raises(ValueError, match="request_id"):
        stream.request("order:new", {}, request_id="", header=headers)

    stream.request("order:new", {}, request_id="request-1", header=headers)
    with pytest.raises(ValueError, match="already pending"):
        stream.request("order:new", {}, request_id="request-1", header=headers)


def test_order_response_resolve_rejects_malformed_response_without_clearing_pending() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")
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

    with pytest.raises(StandXError) as caught:
        stream.resolve({"request_id": "request-1"})

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert stream.pending_request_ids == {"request-1"}


def test_order_response_resolve_rejects_a_different_session_without_clearing_pending() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")
    stream.request(
        "order:new",
        {"qty": "0.1"},
        request_id="request-1",
        header={
            "x-request-id": "request-1",
            "x-request-timestamp": "1700000000000",
            "x-request-signature": "signature",
        },
    )

    with pytest.raises(StandXError) as caught:
        stream.resolve(
            {"session_id": "session-2", "request_id": "request-1", "code": 0}
        )

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.request_id == "request-1"
    assert stream.pending_request_ids == {"request-1"}


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


def test_stream_protocol_errors_use_stable_sdk_error_code() -> None:
    response_stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1", session_id="session-1"
    )
    market_stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    with pytest.raises(StandXError) as response_error:
        response_stream.decode_response({"code": 0})
    with pytest.raises(StandXError) as market_error:
        market_stream.decode({"channel": "order"})

    assert response_error.value.code is ErrorCode.PROTOCOL_ERROR
    assert market_error.value.code is ErrorCode.PROTOCOL_ERROR


def test_stream_decoders_reject_non_object_envelopes_as_protocol_errors() -> None:
    response_stream = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1", session_id="session-1"
    )
    market_stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    with pytest.raises(StandXError) as response_error:
        response_stream.decode_response([])  # type: ignore[arg-type]
    with pytest.raises(StandXError) as market_error:
        market_stream.decode([])  # type: ignore[arg-type]

    assert response_error.value.code is ErrorCode.PROTOCOL_ERROR
    assert market_error.value.code is ErrorCode.PROTOCOL_ERROR


def test_market_stream_normalizes_missing_required_fields_to_protocol_error() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    with pytest.raises(StandXError) as caught:
        stream.decode({"channel": "price", "data": {"symbol": "BTC-USD"}})

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


def test_market_stream_normalizes_invalid_decimal_to_protocol_error() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    with pytest.raises(StandXError) as caught:
        stream.decode(
            {
                "channel": "price",
                "data": {"symbol": "BTC-USD", "last_price": "not-a-decimal"},
            }
        )

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


def test_market_stream_keeps_unknown_channel_as_value_error() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    with pytest.raises(ValueError, match="unsupported StandX Market Stream channel"):
        stream.decode({"channel": "unknown", "data": {}})


def test_order_response_rejects_response_from_different_session() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    with pytest.raises(StandXError) as caught:
        stream.decode_response(
            {"session_id": "session-2", "request_id": "request-1", "code": 0}
        )

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert caught.value.request_id == "request-1"


def test_order_response_stream_rejects_non_numeric_code_as_protocol_error() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    with pytest.raises(StandXError) as caught:
        stream.decode_response({"request_id": "request-1", "code": "invalid"})

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert stream.pending_request_ids == set()


def test_order_response_stream_rejects_boolean_code_as_protocol_error() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    with pytest.raises(StandXError) as caught:
        stream.decode_response({"request_id": "request-1", "code": True})

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR


def test_stream_receive_wraps_invalid_json_as_protocol_error() -> None:
    class InvalidMessageTransport(FakeTransport):
        async def receive(self) -> str:
            return "not-json"

    market = MarketStream(
        "wss://perps.standx.com/ws-stream/v1", transport=InvalidMessageTransport()  # type: ignore[arg-type]
    )
    order_response = OrderResponseStream(
        "wss://perps.standx.com/ws-api/v1",
        session_id="session-1",
        transport=InvalidMessageTransport(),  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        await market.connect()
        await order_response.connect()
        with pytest.raises(StandXError) as market_error:
            await market.receive()
        with pytest.raises(StandXError) as order_error:
            await order_response.receive()
        assert market_error.value.code is ErrorCode.PROTOCOL_ERROR
        assert order_error.value.code is ErrorCode.PROTOCOL_ERROR

    asyncio.run(scenario())
