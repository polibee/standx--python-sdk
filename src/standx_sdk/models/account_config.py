"""Typed leverage and margin configuration DTOs."""

from dataclasses import dataclass

from .order import MarginMode


@dataclass(frozen=True, slots=True)
class PositionConfig:
    symbol: str
    leverage: int
    margin_mode: MarginMode


@dataclass(frozen=True, slots=True)
class ConfigChangeResult:
    code: int
    message: str
    request_id: str
