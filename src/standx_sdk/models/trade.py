"""Typed trade and funding DTOs returned by StandX REST."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RecentTrade:
    symbol: str
    price: Decimal
    qty: Decimal
    quote_qty: Decimal
    is_buyer_taker: bool
    time: str | None = None


@dataclass(frozen=True, slots=True)
class UserTrade:
    id: int
    order_id: int
    symbol: str
    side: str
    price: Decimal
    qty: Decimal
    value: Decimal
    fee_asset: str
    fee_qty: Decimal
    pnl: Decimal
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class FundingPayment:
    id: int
    asset: str
    symbol: str
    qty: Decimal
    txn_type: str
    transact_time: str
    created_at: str | None = None
    updated_at: str | None = None
