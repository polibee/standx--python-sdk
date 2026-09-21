"""Typed DTOs for StandX Market Stream events."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class UserOrderEvent:
    id: int
    status: str
    qty: Decimal
    symbol: str | None = None
    side: str | None = None
    order_type: str | None = None
    price: Decimal | None = None
    fill_qty: Decimal | None = None
    fill_avg_price: Decimal | None = None
    cl_ord_id: str | None = None
    reduce_only: bool = False
    time_in_force: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class PositionEvent:
    id: int
    qty: Decimal
    leverage: int
    symbol: str | None = None
    entry_price: Decimal | None = None
    entry_value: Decimal | None = None
    margin_mode: str | None = None
    status: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class BalanceEvent:
    token: str
    total: Decimal
    free: Decimal | None = None
    locked: Decimal | None = None
    occupied: Decimal | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class UserTradeEvent:
    id: int
    symbol: str
    qty: Decimal
    price: Decimal
    order_id: int | None = None
    fee_qty: Decimal | None = None
    fee_asset: str | None = None


@dataclass(frozen=True, slots=True)
class OrderResponseEvent:
    request_id: str
    code: int
    state: str
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PriceEvent:
    symbol: str
    last_price: Decimal
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    mid_price: Decimal | None = None
    spread: tuple[Decimal, Decimal] | None = None


@dataclass(frozen=True, slots=True)
class DepthBookEvent:
    symbol: str
    asks: tuple[tuple[Decimal, Decimal], ...]
    bids: tuple[tuple[Decimal, Decimal], ...]


@dataclass(frozen=True, slots=True)
class PublicTradeEvent:
    id: int
    symbol: str
    price: Decimal
    qty: Decimal
    side: str | None = None
