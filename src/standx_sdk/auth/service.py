"""StandX wallet-signature authentication flow."""

import base64
import json
from typing import Any, Protocol

from nacl.signing import SigningKey

from .models import LoginResponse
from .signers import WalletSigner


class AuthTransport(Protocol):
    async def post(
        self,
        path: str,
        *,
        params: dict[str, str],
        json: dict[str, object],
    ) -> dict[str, object]: ...


_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58[remainder] + encoded
    return _BASE58[0] * (len(value) - len(value.lstrip(b"\0"))) + (encoded or _BASE58[0])


def _jwt_payload(token: str) -> dict[str, Any]:
    try:
        encoded = token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        return json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("signedData is not a valid JWT") from exc


class AuthService:
    def __init__(self, transport: AuthTransport, signer: WalletSigner) -> None:
        self._transport = transport
        self._signer = signer
        self.token: str | None = None

    async def login(self, expires_seconds: int = 604800) -> LoginResponse:
        temporary_key = SigningKey.generate()
        request_id = _base58_encode(bytes(temporary_key.verify_key))
        prepared = await self._transport.post(
            "/v1/offchain/prepare-signin",
            params={"chain": self._signer.chain},
            json={"address": self._signer.address, "requestId": request_id},
        )
        if prepared.get("success") is not True:
            raise ValueError("failed to prepare sign-in")
        signed_data = prepared.get("signedData")
        if not isinstance(signed_data, str):
            raise ValueError("prepare-signin did not return signedData")
        payload = _jwt_payload(signed_data)
        message = payload.get("message")
        if not isinstance(message, str):
            raise ValueError("signedData payload did not contain message")
        signature = await self._signer.sign_login_message(message)
        response = await self._transport.post(
            "/v1/offchain/login",
            params={"chain": self._signer.chain},
            json={"signature": signature, "signedData": signed_data, "expiresSeconds": expires_seconds},
        )
        result = LoginResponse(
            token=str(response["token"]),
            address=str(response["address"]),
            alias=str(response.get("alias", "")),
            chain=str(response["chain"]),
            perps_alpha=bool(response.get("perpsAlpha", False)),
        )
        self.token = result.token
        return result
