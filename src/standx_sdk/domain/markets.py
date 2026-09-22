import asyncio
from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar, cast

from ..errors import ErrorCode, StandXError
from ..models.market import (
    DepthBook,
    InstrumentRules,
    MarketOverview,
    MarketOverviewSymbol,
    SymbolMarket,
    SymbolPrice,
)
from ..models.trade import RecentTrade
from ..transport.http import HttpTransport

_T = TypeVar("_T")


class MarketsApi:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport
        self._symbol_info_cache: dict[str, InstrumentRules] = {}
        self._symbol_info_locks: dict[str, asyncio.Lock] = {}

    async def symbol_info(self, symbol: str, *, refresh: bool = False) -> InstrumentRules:
        if not refresh and symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        lock = self._symbol_info_locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            if not refresh and symbol in self._symbol_info_cache:
                return self._symbol_info_cache[symbol]
            values: list[dict[str, Any]] = await self._transport.get(
                "/api/query_symbol_info", params={"symbol": symbol}
            )
            rules = _protocol_decode(
                "query_symbol_info",
                lambda: _instrument_rules(values),
            )
            self._symbol_info_cache[symbol] = rules
            return rules

    def clear_symbol_info_cache(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._symbol_info_cache.clear()
        else:
            self._symbol_info_cache.pop(symbol, None)

    async def overview(self) -> MarketOverview:
        response = await self._transport.get("/api/query_market_overview")
        return _protocol_decode(
            "query_market_overview",
            lambda: _market_overview(response),
        )

    async def symbol_market(self, symbol: str) -> SymbolMarket:
        response = await self._transport.get(
            "/api/query_symbol_market", params={"symbol": symbol}
        )
        return _protocol_decode("query_symbol_market", lambda: _symbol_market(response))

    async def symbol_price(self, symbol: str) -> SymbolPrice:
        value = await self._transport.get(
            "/api/query_symbol_price", params={"symbol": symbol}
        )
        return _protocol_decode(
            "query_symbol_price",
            lambda: SymbolPrice(
                symbol=str(value["symbol"]),
                last_price=_optional_decimal(value.get("last_price")),
                mark_price=_optional_decimal(value.get("mark_price")),
                index_price=_optional_decimal(value.get("index_price")),
                mid_price=_optional_decimal(value.get("mid_price")),
                spread_bid=_optional_decimal(value.get("spread_bid")),
                spread_ask=_optional_decimal(value.get("spread_ask")),
                base=value.get("base") if isinstance(value.get("base"), str) else None,
                quote=value.get("quote") if isinstance(value.get("quote"), str) else None,
                time=value.get("time"),
            ),
        )

    async def depth_book(self, symbol: str) -> DepthBook:
        value = await self._transport.get(
            "/api/query_depth_book", params={"symbol": symbol}
        )
        return _protocol_decode(
            "query_depth_book",
            lambda: DepthBook(
                symbol=str(value["symbol"]),
                asks=_levels(value.get("asks", [])),
                bids=_levels(value.get("bids", [])),
            ),
        )

    async def _recent_trades_raw(
        self, symbol: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, object] = {"symbol": symbol}
        if limit is not None:
            params["limit"] = limit
        response = await self._transport.get("/api/query_recent_trades", params=params)
        values = response.get("result", response) if isinstance(response, dict) else response
        return cast(list[dict[str, Any]], values)

    async def recent_trades(
        self, symbol: str, *, limit: int | None = None
    ) -> list[RecentTrade]:
        values = await self._recent_trades_raw(symbol, limit=limit)
        return _protocol_decode(
            "query_recent_trades",
            lambda: [
                RecentTrade(
                    symbol=str(value["symbol"]),
                    price=Decimal(str(value["price"])),
                    qty=Decimal(str(value["qty"])),
                    quote_qty=Decimal(str(value["quote_qty"])),
                    is_buyer_taker=bool(value["is_buyer_taker"]),
                    time=value.get("time") if isinstance(value.get("time"), str) else None,
                )
                for value in values
            ],
        )

    async def recent_trade_snapshots(
        self, symbol: str, *, limit: int | None = None
    ) -> list[RecentTrade]:
        return await self.recent_trades(symbol, limit=limit)


__all__ = ["MarketsApi"]


def _protocol_decode(endpoint: str, decoder: Callable[[], _T]) -> _T:
    try:
        return decoder()
    except StandXError:
        raise
    except (ArithmeticError, IndexError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StandXError(
            ErrorCode.PROTOCOL_ERROR,
            f"malformed response from {endpoint}",
            retryable=False,
        ) from exc


def _instrument_rules(values: list[dict[str, Any]]) -> InstrumentRules:
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
        enabled=value.get("enabled") if isinstance(value.get("enabled"), bool) else None,
        created_at=value.get("created_at") if isinstance(value.get("created_at"), str) else None,
        updated_at=value.get("updated_at") if isinstance(value.get("updated_at"), str) else None,
    )


def _market_overview(response: dict[str, Any]) -> MarketOverview:
    summary = response["summary"]
    return MarketOverview(
        open_interest_notional=Decimal(str(summary["open_interest_notional"])),
        symbol_count=int(summary["symbol_count"]),
        volume_quote_24h=Decimal(str(summary["volume_quote_24h"])),
        symbols=tuple(_overview_symbol(value) for value in response["symbols"]),
    )


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _levels(value: Any) -> tuple[tuple[Decimal, Decimal], ...]:
    return tuple((Decimal(str(level[0])), Decimal(str(level[1]))) for level in value)


def _spread(value: Any) -> tuple[Decimal, Decimal] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    return Decimal(str(value[0])), Decimal(str(value[1]))


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
        base=value.get("base") if isinstance(value.get("base"), str) else None,
        quote=value.get("quote") if isinstance(value.get("quote"), str) else None,
        mark_price=_optional_decimal(value.get("mark_price")),
        index_price=_optional_decimal(value.get("index_price")),
        mid_price=_optional_decimal(value.get("mid_price")),
        high_price_24h=_optional_decimal(value.get("high_price_24h")),
        low_price_24h=_optional_decimal(value.get("low_price_24h")),
        open_interest=_optional_decimal(value.get("open_interest")),
        volume_24h=_optional_decimal(value.get("volume_24h")),
        spread=_spread(value.get("spread")),
        next_funding_time=value.get("next_funding_time"),
        time=value.get("time"),
    )
