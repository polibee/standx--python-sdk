import asyncio

import pytest

from standx_sdk.auth.service import AuthService
from standx_sdk.auth.wallet import WalletSigner
from standx_sdk.errors import ErrorCode, StandXError


def test_wallet_signer_protocol_requires_login_message_method() -> None:
    assert hasattr(WalletSigner, "sign_login_message")


def test_empty_wallet_address_is_rejected() -> None:
    with pytest.raises(ValueError, match="address"):
        WalletSigner(chain="bsc", address="")


class FakeAuthTransport:
    async def post(
        self, path: str, *, params: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]:
        if path.endswith("prepare-signin"):
            return {"success": True, "signedData": "header.eyJtZXNzYWdlIjoic2lnbiJ9.signature"}
        return {
            "token": "jwt-token",
            "address": "0xabc",
            "alias": "alice",
            "chain": "bsc",
            "perpsAlpha": True,
        }


class FakeWallet(WalletSigner):
    async def sign_login_message(self, message: str) -> str:
        return f"signed:{message}"


def test_auth_service_runs_documented_prepare_and_login_flow() -> None:
    auth = AuthService(FakeAuthTransport(), FakeWallet(chain="bsc", address="0xabc"))

    result = asyncio.run(auth.login())

    assert result.token == "jwt-token"
    assert auth.token == "jwt-token"


def test_auth_service_maps_prepare_rejection_to_auth_error() -> None:
    class RejectingTransport(FakeAuthTransport):
        async def post(
            self, path: str, *, params: dict[str, str], json: dict[str, object]
        ) -> dict[str, object]:
            return {"success": False, "message": "signature rejected"}

    auth = AuthService(RejectingTransport(), FakeWallet(chain="bsc", address="0xabc"))

    with pytest.raises(StandXError) as caught:
        asyncio.run(auth.login())

    assert caught.value.code is ErrorCode.AUTH_FAILED
    assert caught.value.message == "failed to prepare sign-in"


def test_auth_service_maps_malformed_signed_data_to_protocol_error() -> None:
    class MalformedTransport(FakeAuthTransport):
        async def post(
            self, path: str, *, params: dict[str, str], json: dict[str, object]
        ) -> dict[str, object]:
            return {"success": True, "signedData": "not-a-jwt"}

    auth = AuthService(MalformedTransport(), FakeWallet(chain="bsc", address="0xabc"))

    with pytest.raises(StandXError) as caught:
        asyncio.run(auth.login())

    assert caught.value.code is ErrorCode.PROTOCOL_ERROR
    assert "token" not in caught.value.message.lower()
