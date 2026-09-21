"""Typed account and position snapshots returned by StandX REST."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    balance: Decimal
    equity: Decimal
    upnl: Decimal
    isolated_balance: Decimal | None = None
    isolated_upnl: Decimal | None = None
    cross_balance: Decimal | None = None
    cross_margin: Decimal | None = None
    cross_upnl: Decimal | None = None
    locked: Decimal | None = None
    cross_available: Decimal | None = None
    pnl_freeze: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    id: int
    symbol: str
    qty: Decimal
    leverage: int
    entry_price: Decimal | None = None
    entry_value: Decimal | None = None
    margin_mode: str | None = None
    status: str | None = None
    realized_pnl: Decimal | None = None
    upnl: Decimal | None = None
    updated_at: str | None = None
