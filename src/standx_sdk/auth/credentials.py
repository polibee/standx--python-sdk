"""Unified credentials for JWT-authenticated signed trading."""

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

    @property
    def request_signer(self) -> Ed25519RequestSigner:
        return Ed25519RequestSigner(self.request_signing_key)
