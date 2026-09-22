import asyncio
import json
from pathlib import Path
from typing import Any

from standx_sdk.auth.service import AuthService
from standx_sdk.auth.wallet import WalletSigner
from standx_sdk.models.stream import OrderResponseEvent, UserOrderEvent
from standx_sdk.streams.market import MarketStream
from standx_sdk.streams.order_response import OrderResponseStream

FIXTURES = Path(__file__).parent / "fixtures" / "standx"


def load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert isinstance(value, dict)
    return value


class FixtureAuthTransport:
    async def post(
        self, path: str, *, params: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]:
        return load_fixture("prepare_signin.json") if path.endswith("prepare-signin") else load_fixture("login.json")


class FixtureWallet(WalletSigner):
    async def sign_login_message(self, message: str) -> str:
        return "fixture-wallet-signature"


def test_documented_auth_fixtures_run_through_wallet_login() -> None:
    auth = AuthService(FixtureAuthTransport(), FixtureWallet(chain="bsc", address="0xabc"))

    result = asyncio.run(auth.login())

    assert result.token == "fixture-jwt-token"
    assert result.chain == "bsc"


def test_documented_market_order_fixture_maps_to_user_order_event() -> None:
    stream = MarketStream("wss://example")

    event = stream.decode(load_fixture("market_order_event.json"))

    assert isinstance(event, UserOrderEvent)
    assert event.cl_ord_id == "client-order-1"
    assert event.reduce_only is False
    assert event.seq == 42


def test_documented_order_response_fixture_maps_to_typed_event() -> None:
    stream = OrderResponseStream("wss://example", session_id="fixture-session")

    event = stream.decode_response(load_fixture("order_response_accepted.json"))

    assert isinstance(event, OrderResponseEvent)
    assert event.request_id == "request-1"
    assert event.state == "accepted"
    assert event.code == 202
