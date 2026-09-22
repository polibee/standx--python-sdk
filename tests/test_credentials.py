import base64
import json

import pytest
from nacl.signing import SigningKey

from standx_sdk import ClientConfig, StandXClient
from standx_sdk.auth.credentials import StandXCredentials


def test_unified_credentials_wire_jwt_and_request_signer_into_client() -> None:
    credentials = StandXCredentials(
        access_token="official-jwt",
        request_signing_key=bytes(range(32)),
    )
    client = StandXClient(
        ClientConfig(base_url="https://paper.example"),
        credentials=credentials,
    )

    stream = client.order_response_stream()

    assert client.auth.token == "official-jwt"
    assert client.http_transport.token == "official-jwt"
    assert stream.token == "official-jwt"
    assert stream.request_signer is not None


def test_unified_credentials_reject_invalid_request_signing_key() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        StandXCredentials(access_token="jwt", request_signing_key=b"short")


@pytest.mark.parametrize(
    ("encoded", "expected"),
    [
        (bytes(range(32)).hex(), bytes(range(32))),
        (base64.b64encode(bytes(range(32))).decode(), bytes(range(32))),
        (base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("="), bytes(range(32))),
        (base64.b64encode(bytes(range(32)) + bytes(range(32))).decode(), bytes(range(32))),
    ],
)
def test_credentials_decode_documented_key_encodings(encoded: str, expected: bytes) -> None:
    assert StandXCredentials.decode_request_signing_key(encoded) == expected


def test_credentials_reject_undefined_key_length_instead_of_truncating() -> None:
    encoded = base64.b64encode(b"x" * 33).decode()

    with pytest.raises(ValueError, match="32-byte"):
        StandXCredentials.decode_request_signing_key(encoded)


def test_credentials_decode_base58_request_signing_key() -> None:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    value = bytes(range(32))
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = alphabet[remainder] + encoded
    encoded = "1" + encoded

    assert StandXCredentials.decode_request_signing_key(encoded) == value


def test_order_response_stream_signs_order_request_from_unified_credentials() -> None:
    credentials = StandXCredentials(
        access_token="official-jwt",
        request_signing_key=bytes(range(32)),
    )
    client = StandXClient(
        ClientConfig(base_url="https://paper.example"),
        credentials=credentials,
    )
    stream = client.order_response_stream(session_id="session-1")

    request = stream.request(
        "order:new",
        {"symbol": "BTC-USD", "qty": "0.1"},
        request_id="request-1",
    )

    header = request["header"]
    assert isinstance(header, dict)
    assert header["x-request-id"] == "request-1"
    assert header["x-request-signature"]
    assert int(header["x-request-timestamp"]) > 0

    payload = json.dumps(
        {"symbol": "BTC-USD", "qty": "0.1"}, separators=(",", ":"), ensure_ascii=False
    )
    message = f"v1,request-1,{header['x-request-timestamp']},{payload}".encode()
    signature = base64.b64decode(header["x-request-signature"])
    SigningKey(bytes(range(32))).verify_key.verify(message, signature)
