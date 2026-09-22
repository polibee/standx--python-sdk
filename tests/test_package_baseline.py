import math

import pytest

from standx_sdk import ClientConfig, Environment


def test_paper_is_the_default_environment() -> None:
    config = ClientConfig(base_url="https://perps.standx.com")

    assert config.environment is Environment.PAPER


def test_client_config_rejects_non_finite_timeout() -> None:
    for timeout in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            ClientConfig(base_url="https://perps.standx.com", timeout_seconds=timeout)
