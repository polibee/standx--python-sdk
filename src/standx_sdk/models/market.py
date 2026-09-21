"""Market metadata returned by StandX."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InstrumentRules:
    symbol: str
    base_asset: str
    base_decimals: int
    quote_asset: str
    quote_decimals: int
    price_tick_decimals: int
    qty_tick_decimals: int
    min_order_qty: Decimal
    max_order_qty: Decimal
    max_position_size: Decimal
    max_leverage: int
    def_leverage: int
    max_open_orders: int
    price_cap_ratio: Decimal
    price_floor_ratio: Decimal
    maker_fee: Decimal
    taker_fee: Decimal
    depth_ticks: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class MarketOverviewSymbol:
    base: str
    quote: str
    symbol: str
    last_price: Decimal
    mark_price: Decimal
    funding_rate: Decimal
    open_interest: Decimal
    open_interest_notional: Decimal
    price_change_pct: float
    volume_24h: Decimal
    volume_quote_24h: Decimal
    time: str


@dataclass(frozen=True, slots=True)
class MarketOverview:
    open_interest_notional: Decimal
    symbol_count: int
    volume_quote_24h: Decimal
    symbols: tuple[MarketOverviewSymbol, ...]


@dataclass(frozen=True, slots=True)
class SymbolMarket:
    symbol: str
    last_price: Decimal | None
    funding_rate: Decimal
    base: str | None = None
    quote: str | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    mid_price: Decimal | None = None
    high_price_24h: Decimal | None = None
    low_price_24h: Decimal | None = None
    open_interest: Decimal | None = None
    volume_24h: Decimal | None = None
    spread: tuple[Decimal, Decimal] | None = None
    next_funding_time: str | None = None
    time: str | None = None


@dataclass(frozen=True, slots=True)
class SymbolPrice:
    symbol: str
    last_price: Decimal | None
    mark_price: Decimal | None
    index_price: Decimal | None
    mid_price: Decimal | None
    spread_bid: Decimal | None
    spread_ask: Decimal | None
    base: str | None = None
    quote: str | None = None
    time: str | None = None


@dataclass(frozen=True, slots=True)
class DepthBook:
    symbol: str
    asks: tuple[tuple[Decimal, Decimal], ...]
    bids: tuple[tuple[Decimal, Decimal], ...]
