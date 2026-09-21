from standx_sdk import ClientConfig, Environment
from standx_sdk.signing.request import Ed25519RequestSigner


def test_client_config_defaults_to_paper_and_live_is_explicit() -> None:
    paper = ClientConfig(base_url="https://paper.example")
    live = ClientConfig(base_url="https://live.example", environment=Environment.LIVE)

    assert paper.environment is Environment.PAPER
    assert live.environment is Environment.LIVE


def test_sensitive_credentials_are_not_part_of_public_config_or_signer_repr() -> None:
    private_key = bytes(range(32))
    config = ClientConfig(base_url="https://paper.example")
    signer = Ed25519RequestSigner(private_key)

    assert "private_key" not in repr(config)
    assert private_key.hex() not in repr(signer)
    assert "Authorization" not in repr(config)
