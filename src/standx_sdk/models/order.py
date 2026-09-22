"""StandX order request and response primitives."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    ALO = "alo"


class MarginMode(str, Enum):
    CROSS = "cross"
    ISOLATED = "isolated"


class OrderStatus(str, Enum):
    OPEN = "open"
    CANCELED = "canceled"
    FILLED = "filled"
    REJECTED = "rejected"
    UNTRIGGERED = "untriggered"


@dataclass(frozen=True, slots=True)
class CreateOrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: Decimal
    time_in_force: TimeInForce
    reduce_only: bool
    price: Decimal | None = None
    cl_ord_id: str | None = None
    margin_mode: MarginMode | str | None = None
    leverage: int | None = None
    tp_price: Decimal | None = None
    sl_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        _require_positive_decimal(self.qty, "qty")
        if self.order_type is OrderType.LIMIT and self.price is None:
            raise ValueError("limit order requires price")
        if self.order_type is OrderType.MARKET and self.price is not None:
            raise ValueError("market order must not include price")
        if self.price is not None:
            _require_positive_decimal(self.price, "price")
        if self.tp_price is not None:
            _require_positive_decimal(self.tp_price, "tp_price")
        if self.sl_price is not None:
            _require_positive_decimal(self.sl_price, "sl_price")
        if self.leverage is not None and self.leverage <= 0:
            raise ValueError("leverage must be positive")
        if self.margin_mode is not None:
            value = self.margin_mode.value if isinstance(self.margin_mode, MarginMode) else self.margin_mode
            if value not in {mode.value for mode in MarginMode}:
                raise ValueError("margin_mode must be cross or isolated")


def _require_positive_decimal(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field} must be finite and positive")


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    cl_ord_id: str | None
    symbol: str
    side: str
    order_type: str
    qty: Decimal
    fill_qty: Decimal
    fill_avg_price: Decimal
    status: str
    time_in_force: str
    reduce_only: bool
    price: Decimal | None = None
    leverage: int | None = None
    margin_mode: str | None = None
    avail_locked: Decimal | None = None
    closed_block: int | None = None
    created_at: str | None = None
    created_block: int | None = None
    liq_id: int | None = None
    margin: Decimal | None = None
    payload: object | None = None
    position_id: int | None = None
    remark: str | None = None
    source: str | None = None
    user: str | None = None
    updated_at: str | None = None
