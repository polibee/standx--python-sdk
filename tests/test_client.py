from standx_sdk import ClientConfig, Environment, StandXClient
from standx_sdk.transport.http import HttpTransport


def test_client_exposes_domain_services_and_stream_factories() -> None:
    client = StandXClient(ClientConfig(base_url="https://perps.standx.com"))

    assert client.config.environment is Environment.PAPER
    assert client.auth is not None
    assert client.markets is not None
    assert client.account is not None
    assert client.orders is not None
    assert client.streams.market() is not None
    assert client.streams.order_response() is not None


def test_client_uses_configured_stream_endpoints_and_injected_http_transport() -> None:
    config = ClientConfig(
        base_url="https://paper.example",
        market_stream_url="wss://paper.example/market",
        order_response_url="wss://paper.example/order",
    )
    transport = HttpTransport("https://injected.example")
    client = StandXClient(config, http_transport=transport)

    assert client.markets._transport is transport
    assert client.streams.market().endpoint == "wss://paper.example/market"
    assert client.streams.order_response(session_id="s").endpoint == "wss://paper.example/order"
