from decimal import Decimal

import pytest

from standx_sdk.errors import OrderValidationError
from standx_sdk.models.market import InstrumentRules
from standx_sdk.models.order import CreateOrderRequest, OrderSide, OrderType, TimeInForce
from standx_sdk.validation.orders import validate_order


def rules() -> InstrumentRules:
    return InstrumentRules(
        symbol="BTC-USD",
        base_asset="BTC",
        base_decimals=9,
        quote_asset="DUSD",
        quote_decimals=9,
        price_tick_decimals=2,
        qty_tick_decimals=4,
        min_order_qty=Decimal("0.0001"),
        max_order_qty=Decimal(100),
        max_position_size=Decimal(10),
        max_leverage=20,
        def_leverage=10,
        max_open_orders=100,
        price_cap_ratio=Decimal("0.3"),
        price_floor_ratio=Decimal("0.3"),
        maker_fee=Decimal("0.0001"),
        taker_fee=Decimal("0.0004"),
        depth_ticks=(Decimal("0.01"),),
    )


def request(**overrides: object) -> CreateOrderRequest:
    values: dict[str, object] = {
        "symbol": "BTC-USD",
        "side": OrderSide.BUY,
        "order_type": OrderType.LIMIT,
        "qty": Decimal("1.0000"),
        "price": Decimal("50000.00"),
        "time_in_force": TimeInForce.GTC,
        "reduce_only": False,
        "leverage": 10,
    }
    values.update(overrides)
    return CreateOrderRequest(**values)  # type: ignore[arg-type]


def test_validate_order_enforces_documented_quantity_and_price_precision() -> None:
    with pytest.raises(OrderValidationError, match="qty"):
        validate_order(request(qty=Decimal("0.00001")), rules())
    with pytest.raises(OrderValidationError, match="price"):
        validate_order(request(price=Decimal("50000.001")), rules())


def test_validate_order_enforces_leverage_and_reduce_only_capacity() -> None:
    with pytest.raises(OrderValidationError, match="leverage"):
        validate_order(request(leverage=21), rules())
    with pytest.raises(OrderValidationError, match="reduce_only"):
        validate_order(
            request(qty=Decimal(4), reduce_only=True),
            rules(),
            position_qty=Decimal(5),
            pending_reduce_only_qty=Decimal(2),
        )


def test_validate_order_requires_leverage_and_margin_mode_to_match_position() -> None:
    with pytest.raises(OrderValidationError, match="position_leverage"):
        validate_order(
            request(leverage=10),
            rules(),
            position_leverage=5,
        )
    with pytest.raises(OrderValidationError, match="margin_mode"):
        validate_order(
            request(margin_mode="isolated"),
            rules(),
            position_margin_mode="cross",
        )


def test_validate_order_accepts_values_aligned_with_symbol_rules() -> None:
    validate_order(
        request(qty=Decimal("0.1234"), price=Decimal("50000.01")),
        rules(),
    )
