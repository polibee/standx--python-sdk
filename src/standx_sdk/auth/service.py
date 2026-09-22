"""StandX wallet-signature authentication flow."""

import base64
import binascii
import json
from collections.abc import Callable
from typing import Any, Protocol, cast

from nacl.signing import SigningKey

from ..errors import ErrorCode, StandXError
from .token import LoginResponse
from .wallet import WalletSigner


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
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("JWT payload must be an object")
        return cast(dict[str, Any], payload)
    except (binascii.Error, IndexError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise StandXError(
            ErrorCode.PROTOCOL_ERROR,
            "signedData is not a valid JWT",
        ) from exc


class AuthService:
    def __init__(
        self,
        transport: AuthTransport,
        signer: WalletSigner | None = None,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> None:
        self._transport = transport
        self._signer = signer
        self._on_token = on_token
        self.token: str | None = None

    async def login(self, expires_seconds: int = 604800) -> LoginResponse:
        if self._signer is None:
            raise ValueError("a wallet signer is required for login")
        temporary_key = SigningKey.generate()
        request_id = _base58_encode(bytes(temporary_key.verify_key))
        prepared = await self._transport.post(
            "/v1/offchain/prepare-signin",
            params={"chain": self._signer.chain},
            json={"address": self._signer.address, "requestId": request_id},
        )
        if not isinstance(prepared, dict):
            raise StandXError(ErrorCode.PROTOCOL_ERROR, "prepare-signin response was not an object")
        if prepared.get("success") is not True:
            raise StandXError(ErrorCode.AUTH_FAILED, "failed to prepare sign-in")
        signed_data = prepared.get("signedData")
        if not isinstance(signed_data, str):
            raise StandXError(ErrorCode.PROTOCOL_ERROR, "prepare-signin did not return signedData")
        payload = _jwt_payload(signed_data)
        message = payload.get("message")
        if not isinstance(message, str):
            raise StandXError(ErrorCode.PROTOCOL_ERROR, "signedData payload did not contain message")
        signature = await self._signer.sign_login_message(message)
        response = await self._transport.post(
            "/v1/offchain/login",
            params={"chain": self._signer.chain},
            json={
                "signature": signature,
                "signedData": signed_data,
                "expiresSeconds": expires_seconds,
            },
        )
        result = _login_response(response)
        self.token = result.token
        if self._on_token is not None:
            self._on_token(result.token)
        return result


def _login_response(response: object) -> LoginResponse:
    try:
        if not isinstance(response, dict):
            raise TypeError("login response must be an object")
        token = response["token"]
        address = response["address"]
        chain = response["chain"]
        alias = response.get("alias", "")
        perps_alpha = response.get("perpsAlpha", False)
        if not all(isinstance(value, str) for value in (token, address, chain, alias)):
            raise TypeError("login response string field has an invalid type")
        if not isinstance(perps_alpha, bool):
            raise TypeError("login response perpsAlpha has an invalid type")
        return LoginResponse(
            token=token,
            address=address,
            alias=alias,
            chain=chain,
            perps_alpha=perps_alpha,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StandXError(
            ErrorCode.PROTOCOL_ERROR,
            "login response did not contain valid authentication fields",
            retryable=False,
        ) from exc
