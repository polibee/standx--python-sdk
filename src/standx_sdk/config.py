"""Client configuration and environment safety boundaries."""

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

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
