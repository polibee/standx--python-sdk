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
