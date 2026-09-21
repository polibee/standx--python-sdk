"""Documented public market endpoints."""

from decimal import Decimal
from typing import Any

from ..models.market import InstrumentRules
from .transport import RestTransport


class MarketsApi:
    def __init__(self, transport: RestTransport) -> None:
        self._transport = transport

    async def symbol_info(self, symbol: str) -> InstrumentRules:
        values: list[dict[str, Any]] = await self._transport.get(
            "/api/query_symbol_info", params={"symbol": symbol}
        )
        value = values[0]
        return InstrumentRules(
            symbol=str(value["symbol"]),
            base_asset=str(value["base_asset"]),
            base_decimals=int(value["base_decimals"]),
            quote_asset=str(value["quote_asset"]),
            quote_decimals=int(value["quote_decimals"]),
            price_tick_decimals=int(value["price_tick_decimals"]),
            qty_tick_decimals=int(value["qty_tick_decimals"]),
            min_order_qty=Decimal(str(value["min_order_qty"])),
            max_order_qty=Decimal(str(value["max_order_qty"])),
            max_position_size=Decimal(str(value["max_position_size"])),
            max_leverage=int(value["max_leverage"]),
            def_leverage=int(value["def_leverage"]),
            max_open_orders=int(value["max_open_orders"]),
            price_cap_ratio=Decimal(str(value["price_cap_ratio"])),
            price_floor_ratio=Decimal(str(value["price_floor_ratio"])),
            maker_fee=Decimal(str(value["maker_fee"])),
            taker_fee=Decimal(str(value["taker_fee"])),
            depth_ticks=tuple(Decimal(item) for item in str(value["depth_ticks"]).split(",")),
        )
