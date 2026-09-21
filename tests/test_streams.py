from standx_sdk.streams.market import MarketStream
from standx_sdk.streams.order_response import OrderResponseStream


def test_market_stream_builds_documented_subscription_envelope() -> None:
    stream = MarketStream("wss://perps.standx.com/ws-stream/v1")

    assert stream.subscription("depth_book", "BTC-USD") == {
        "subscribe": {"channel": "depth_book", "symbol": "BTC-USD"}
    }


def test_order_response_stream_builds_documented_request_envelope() -> None:
    stream = OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id="session-1")

    message = stream.request("order:new", {"qty": "0.1"}, request_id="request-1")

    assert message["session_id"] == "session-1"
    assert message["request_id"] == "request-1"
    assert message["method"] == "order:new"
    assert message["params"] == '{"qty":"0.1"}'
