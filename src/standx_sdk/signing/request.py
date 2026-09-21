"""StandX ed25519 request-body signing."""

import base64

from nacl.signing import SigningKey


class Ed25519RequestSigner:
    def __init__(self, private_key: bytes) -> None:
        if len(private_key) != 32:
            raise ValueError("ed25519 private key must be 32 bytes")
        self._key = SigningKey(private_key)

    def sign_request(
        self,
        version: str,
        request_id: str,
        timestamp: int,
        payload: str,
    ) -> dict[str, str]:
        message = f"{version},{request_id},{timestamp},{payload}".encode()
        signature = self._key.sign(message).signature
        return {
            "x-request-sign-version": version,
            "x-request-id": request_id,
            "x-request-timestamp": str(timestamp),
            "x-request-signature": base64.b64encode(signature).decode("ascii"),
        }
