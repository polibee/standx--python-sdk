from standx_sdk.signing.request import Ed25519RequestSigner


def test_request_signature_matches_fixed_standx_vector() -> None:
    signer = Ed25519RequestSigner(bytes(range(32)))

    headers = signer.sign_request(
        version="v1",
        request_id="req-1",
        timestamp=1700000000000,
        payload='{"qty":"0.1"}',
    )

    assert headers == {
        "x-request-sign-version": "v1",
        "x-request-id": "req-1",
        "x-request-timestamp": "1700000000000",
        "x-request-signature": "Ck6QSNPZzx7t+k67o8E8Zkho1GJuCQqo7aDW1FUf8piTRKPMn1zrddgfB0k/67+VtrlRANd7MPimqcJ8WemmDg==",
    }
