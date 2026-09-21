import asyncio

import httpx

from standx_sdk import ClientConfig, Environment, StandXClient
from standx_sdk.auth.wallet import WalletSigner
from standx_sdk.signing.request import Ed25519RequestSigner
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


def test_client_injects_request_signer_into_default_rest_transport() -> None:
    request_signer = Ed25519RequestSigner(bytes(range(32)))

    client = StandXClient(
        ClientConfig(base_url="https://paper.example"),
        request_signer=request_signer,
    )

    assert client.http_transport._request_signer is request_signer


def test_client_stream_factories_accept_offline_transports() -> None:
    class FakeStreamTransport:
        pass

    transport = FakeStreamTransport()
    client = StandXClient(ClientConfig(base_url="https://paper.example"))

    market = client.streams.market(transport=transport)  # type: ignore[arg-type]
    order_response = client.streams.order_response(
        session_id="s", transport=transport  # type: ignore[arg-type]
    )

    assert market.transport is transport
    assert order_response.transport is transport


class FakeAuthTransport:
    async def post(
        self, path: str, *, params: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]:
        if path.endswith("prepare-signin"):
            return {"success": True, "signedData": "header.eyJtZXNzYWdlIjoic2lnbiJ9.signature"}
        return {
            "token": "client-jwt",
            "address": "0xabc",
            "chain": "bsc",
        }


class FakeWallet(WalletSigner):
    async def sign_login_message(self, message: str) -> str:
        return f"signature:{message}"


def test_client_login_propagates_token_to_shared_rest_transport() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={"balance": "1", "equity": "1", "upnl": "0"})

    rest = HttpTransport("https://paper.example", httpx.MockTransport(handler))
    client = StandXClient(
        ClientConfig(base_url="https://paper.example"),
        FakeWallet(chain="bsc", address="0xabc"),
        http_transport=rest,
        auth_transport=FakeAuthTransport(),
    )

    async def scenario() -> None:
        await client.auth.login()
        await client.account.balance()

    asyncio.run(scenario())
    assert seen["authorization"] == "Bearer client-jwt"


def test_client_close_closes_created_streams_and_auth_transport() -> None:
    auth_transport = FakeAuthTransport()
    auth_transport.closed = False

    async def close_auth() -> None:
        auth_transport.closed = True

    auth_transport.aclose = close_auth  # type: ignore[attr-defined]
    client = StandXClient(
        ClientConfig(base_url="https://paper.example"),
        auth_transport=auth_transport,
    )
    market = client.streams.market()
    order_response = client.streams.order_response()

    asyncio.run(client.close_async())

    assert market.closed is True
    assert order_response.closed is True
    assert auth_transport.closed is True
