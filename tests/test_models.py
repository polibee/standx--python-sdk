from decimal import Decimal

import pytest

from standx_sdk.models.market import InstrumentRules
from standx_sdk.models.order import (
    CreateOrderRequest,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)


def test_standx_order_enums_are_exact() -> None:
    assert OrderType.LIMIT.value == "limit"
    assert OrderType.MARKET.value == "market"
    assert TimeInForce.ALO.value == "alo"
    assert OrderStatus.UNTRIGGERED.value == "untriggered"


def test_limit_order_requires_a_price() -> None:
    with pytest.raises(ValueError, match="price"):
        CreateOrderRequest(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            qty=Decimal("0.1"),
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
        )


def test_market_order_does_not_accept_a_price() -> None:
    with pytest.raises(ValueError, match="price"):
        CreateOrderRequest(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=Decimal("0.1"),
            price=Decimal(50000),
            time_in_force=TimeInForce.IOC,
            reduce_only=False,
        )


def test_order_margin_mode_is_limited_to_documented_values() -> None:
    request = CreateOrderRequest(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        qty=Decimal("0.1"),
        time_in_force=TimeInForce.IOC,
        reduce_only=False,
        margin_mode=MarginMode.ISOLATED,
    )
    assert request.margin_mode is MarginMode.ISOLATED

    with pytest.raises(ValueError, match="margin_mode"):
        CreateOrderRequest(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=Decimal("0.1"),
            time_in_force=TimeInForce.IOC,
            reduce_only=False,
            margin_mode="hedged",
        )


def test_instrument_rules_keep_documented_decimal_constraints() -> None:
    rules = InstrumentRules(
        symbol="BTC-USD",
        base_asset="BTC",
        base_decimals=9,
        quote_asset="DUSD",
        quote_decimals=9,
        price_tick_decimals=2,
        qty_tick_decimals=4,
        min_order_qty=Decimal("0.0001"),
        max_order_qty=Decimal(100),
        max_position_size=Decimal(1000),
        max_leverage=20,
        def_leverage=10,
        max_open_orders=100,
        price_cap_ratio=Decimal("0.3"),
        price_floor_ratio=Decimal("0.3"),
        maker_fee=Decimal("0.0001"),
        taker_fee=Decimal("0.0004"),
        depth_ticks=(Decimal("0.01"), Decimal("0.1"), Decimal(1)),
    )

    assert rules.qty_tick_decimals == 4
    assert rules.max_leverage == 20
