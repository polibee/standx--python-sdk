from standx_sdk import ClientConfig, Environment, StandXClient


def test_client_exposes_domain_services_and_stream_factories() -> None:
    client = StandXClient(ClientConfig(base_url="https://perps.standx.com"))

    assert client.config.environment is Environment.PAPER
    assert client.auth is not None
    assert client.markets is not None
    assert client.account is not None
    assert client.orders is not None
    assert client.streams.market() is not None
    assert client.streams.order_response() is not None
