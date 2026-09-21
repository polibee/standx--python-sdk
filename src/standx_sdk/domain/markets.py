from decimal import Decimal
from typing import Any, cast

from ..models.market import (
    DepthBook,
    InstrumentRules,
    MarketOverview,
    MarketOverviewSymbol,
    SymbolMarket,
    SymbolPrice,
)
from ..transport.http import HttpTransport


class MarketsApi:
    def __init__(self, transport: HttpTransport) -> None:
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

    async def overview(self) -> MarketOverview:
        response = await self._transport.get("/api/query_market_overview")
        summary = response["summary"]
        return MarketOverview(
            open_interest_notional=Decimal(str(summary["open_interest_notional"])),
            symbol_count=int(summary["symbol_count"]),
            volume_quote_24h=Decimal(str(summary["volume_quote_24h"])),
            symbols=tuple(_overview_symbol(value) for value in response["symbols"]),
        )

    async def symbol_market(self, symbol: str) -> SymbolMarket:
        return _symbol_market(
            await self._transport.get("/api/query_symbol_market", params={"symbol": symbol})
        )

    async def symbol_price(self, symbol: str) -> SymbolPrice:
        value = await self._transport.get(
            "/api/query_symbol_price", params={"symbol": symbol}
        )
        return SymbolPrice(
            symbol=str(value["symbol"]),
            last_price=_optional_decimal(value.get("last_price")),
            mark_price=_optional_decimal(value.get("mark_price")),
            index_price=_optional_decimal(value.get("index_price")),
            mid_price=_optional_decimal(value.get("mid_price")),
            spread_bid=_optional_decimal(value.get("spread_bid")),
            spread_ask=_optional_decimal(value.get("spread_ask")),
            time=value.get("time"),
        )

    async def depth_book(self, symbol: str) -> DepthBook:
        value = await self._transport.get(
            "/api/query_depth_book", params={"symbol": symbol}
        )
        return DepthBook(
            symbol=str(value["symbol"]),
            asks=_levels(value.get("asks", [])),
            bids=_levels(value.get("bids", [])),
        )

    async def recent_trades(self, symbol: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, object] = {"symbol": symbol}
        if limit is not None:
            params["limit"] = limit
        response = await self._transport.get("/api/query_recent_trades", params=params)
        values = response.get("result", response) if isinstance(response, dict) else response
        return cast(list[dict[str, Any]], values)


__all__ = ["MarketsApi"]


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _levels(value: Any) -> tuple[tuple[Decimal, Decimal], ...]:
    return tuple((Decimal(str(level[0])), Decimal(str(level[1]))) for level in value)


def _overview_symbol(value: dict[str, Any]) -> MarketOverviewSymbol:
    return MarketOverviewSymbol(
        base=str(value["base"]),
        quote=str(value["quote"]),
        symbol=str(value["symbol"]),
        last_price=Decimal(str(value["last_price"])),
        mark_price=Decimal(str(value["mark_price"])),
        funding_rate=Decimal(str(value["funding_rate"])),
        open_interest=Decimal(str(value["open_interest"])),
        open_interest_notional=Decimal(str(value["open_interest_notional"])),
        price_change_pct=float(value["price_change_pct"]),
        volume_24h=Decimal(str(value["volume_24h"])),
        volume_quote_24h=Decimal(str(value["volume_quote_24h"])),
        time=str(value["time"]),
    )


def _symbol_market(value: dict[str, Any]) -> SymbolMarket:
    return SymbolMarket(
        symbol=str(value["symbol"]),
        last_price=_optional_decimal(value.get("last_price")),
        funding_rate=Decimal(str(value["funding_rate"])),
        mark_price=_optional_decimal(value.get("mark_price")),
        index_price=_optional_decimal(value.get("index_price")),
        mid_price=_optional_decimal(value.get("mid_price")),
        high_price_24h=_optional_decimal(value.get("high_price_24h")),
        low_price_24h=_optional_decimal(value.get("low_price_24h")),
        open_interest=_optional_decimal(value.get("open_interest")),
        volume_24h=_optional_decimal(value.get("volume_24h")),
        next_funding_time=value.get("next_funding_time"),
        time=value.get("time"),
    )
