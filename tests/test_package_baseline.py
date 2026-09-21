from standx_sdk import ClientConfig, Environment


def test_paper_is_the_default_environment() -> None:
    config = ClientConfig(base_url="https://perps.standx.com")

    assert config.environment is Environment.PAPER
