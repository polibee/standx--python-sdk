import asyncio

import pytest

from standx_sdk.auth.service import AuthService
from standx_sdk.auth.signers import WalletSigner


def test_wallet_signer_protocol_requires_login_message_method() -> None:
    assert hasattr(WalletSigner, "sign_login_message")


def test_empty_wallet_address_is_rejected() -> None:
    with pytest.raises(ValueError, match="address"):
        WalletSigner(chain="bsc", address="")


class FakeAuthTransport:
    async def post(self, path: str, *, params: dict[str, str], json: dict[str, object]) -> dict[str, object]:
        if path.endswith("prepare-signin"):
            return {"success": True, "signedData": "header.eyJtZXNzYWdlIjoic2lnbiJ9.signature"}
        return {"token": "jwt-token", "address": "0xabc", "alias": "alice", "chain": "bsc", "perpsAlpha": True}


class FakeWallet(WalletSigner):
    async def sign_login_message(self, message: str) -> str:
        return f"signed:{message}"


def test_auth_service_runs_documented_prepare_and_login_flow() -> None:
    auth = AuthService(FakeAuthTransport(), FakeWallet(chain="bsc", address="0xabc"))

    result = asyncio.run(auth.login())

    assert result.token == "jwt-token"
    assert auth.token == "jwt-token"
