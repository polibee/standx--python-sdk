"""Unified credentials for JWT-authenticated signed trading."""

import base64
import binascii
from dataclasses import dataclass, field

from ..signing.request import Ed25519RequestSigner


@dataclass(frozen=True, slots=True)
class StandXCredentials:
    """Pair an official JWT with its matching Ed25519 request-signing key."""

    access_token: str = field(repr=False)
    request_signing_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.access_token, str) or not self.access_token.strip():
            raise ValueError("access_token must not be blank")
        if not isinstance(self.request_signing_key, bytes):
            raise TypeError("request_signing_key must be bytes")
        if len(self.request_signing_key) != 32:
            raise ValueError("request_signing_key must be exactly 32 bytes")

    @staticmethod
    def decode_request_signing_key(encoded: str) -> bytes:
        """Decode an official Ed25519 key representation without guessing.

        StandX signs requests with a 32-byte Ed25519 secret. API Token values
        may be base58-encoded; the Solana wallet example may expose a 64-byte
        secret key whose first 32 bytes are the Ed25519 secret. Other lengths
        are rejected rather than silently truncated.
        """

        if not isinstance(encoded, str) or not encoded.strip():
            raise ValueError("request signing key must not be blank")
        value = encoded.strip()
        decoded: bytes | None = None
        if len(value) in {64, 128}:
            try:
                decoded = bytes.fromhex(value)
            except ValueError:
                decoded = None
        if decoded is None and all(char in _BASE58_ALPHABET for char in value):
            decoded = _decode_base58(value)
        if decoded is None:
            padded = value + "=" * (-len(value) % 4)
            try:
                decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("request signing key must be hex, base58, or base64") from exc
        if len(decoded) == 64:
            decoded = decoded[:32]
        if len(decoded) != 32:
            raise ValueError("request signing key must decode to a 32-byte Ed25519 key")
        return decoded

    @property
    def request_signer(self) -> Ed25519RequestSigner:
        return Ed25519RequestSigner(self.request_signing_key)


_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _decode_base58(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + _BASE58_ALPHABET.index(char)
    decoded = b"" if number == 0 else number.to_bytes((number.bit_length() + 7) // 8, "big")
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading_zeroes + decoded
