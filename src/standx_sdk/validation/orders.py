"""Order validation using the server-provided symbol information."""

from decimal import Decimal

from ..errors import OrderValidationError
from ..models.market import InstrumentRules
from ..models.order import CreateOrderRequest


def validate_order(
    request: CreateOrderRequest,
    rules: InstrumentRules,
    *,
    position_qty: Decimal | None = None,
    pending_reduce_only_qty: Decimal = Decimal(0),
    position_leverage: int | None = None,
    position_margin_mode: str | None = None,
) -> None:
    if request.symbol != rules.symbol:
        raise OrderValidationError("symbol", request.symbol, f"symbol must be {rules.symbol}")
    if request.qty < rules.min_order_qty:
        raise OrderValidationError("qty", request.qty, f"qty >= {rules.min_order_qty}")
    if request.qty > rules.max_order_qty:
        raise OrderValidationError("qty", request.qty, f"qty <= {rules.max_order_qty}")
    if request.qty > rules.max_position_size:
        raise OrderValidationError("qty", request.qty, f"qty <= {rules.max_position_size}")
    if _decimal_places(request.qty) > rules.qty_tick_decimals:
        raise OrderValidationError("qty", request.qty, f"at most {rules.qty_tick_decimals} decimals")
    if request.price is not None and _decimal_places(request.price) > rules.price_tick_decimals:
        raise OrderValidationError(
            "price", request.price, f"at most {rules.price_tick_decimals} decimals"
        )
    for field, value in (("tp_price", request.tp_price), ("sl_price", request.sl_price)):
        if value is not None and _decimal_places(value) > rules.price_tick_decimals:
            raise OrderValidationError(
                field, value, f"at most {rules.price_tick_decimals} decimals"
            )
    if request.leverage is not None and request.leverage > rules.max_leverage:
        raise OrderValidationError("leverage", request.leverage, f"leverage <= {rules.max_leverage}")
    if (
        request.leverage is not None
        and position_leverage is not None
        and request.leverage != position_leverage
    ):
        raise OrderValidationError(
            "position_leverage", request.leverage, f"must equal {position_leverage}"
        )
    if (
        request.margin_mode is not None
        and position_margin_mode is not None
        and request.margin_mode != position_margin_mode
    ):
        raise OrderValidationError(
            "margin_mode", request.margin_mode, f"must equal {position_margin_mode}"
        )
    if request.reduce_only:
        if position_qty is None:
            raise OrderValidationError("reduce_only", request.qty, "position_qty is required")
        available = position_qty - pending_reduce_only_qty
        if request.qty > available:
            raise OrderValidationError("reduce_only", request.qty, f"qty <= {available}")


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0
