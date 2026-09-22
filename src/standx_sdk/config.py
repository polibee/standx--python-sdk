"""Client configuration and environment safety boundaries."""

import math
from dataclasses import dataclass
from enum import Enum


class Environment(str, Enum):
    """Supported SDK environments."""

    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """Configuration shared by all SDK services."""

    base_url: str
    environment: Environment = Environment.PAPER
    timeout_seconds: float = 10.0
    auth_base_url: str = "https://api.standx.com"
    market_stream_url: str = "wss://perps.standx.com/ws-stream/v1"
    order_response_url: str = "wss://perps.standx.com/ws-api/v1"

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        for name, value in (
            ("auth_base_url", self.auth_base_url),
            ("market_stream_url", self.market_stream_url),
            ("order_response_url", self.order_response_url),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
