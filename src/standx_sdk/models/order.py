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
    margin_mode: str | None = None
    leverage: int | None = None
    tp_price: Decimal | None = None
    sl_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.qty <= 0:
            raise ValueError("qty must be positive")
        if self.order_type is OrderType.LIMIT and self.price is None:
            raise ValueError("limit order requires price")
        if self.order_type is OrderType.MARKET and self.price is not None:
            raise ValueError("market order must not include price")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")
        if self.leverage is not None and self.leverage <= 0:
            raise ValueError("leverage must be positive")
