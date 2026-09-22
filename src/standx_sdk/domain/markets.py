import asyncio
from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar, cast

from ..errors import ErrorCode, StandXError
from ..models.market import (
    DepthBook,
    InstrumentRules,
    KlineBar,
    KlineHistory,
    KlineResolution,
    MarketOverview,
    MarketOverviewSymbol,
    SymbolMarket,
    SymbolPrice,
)
from ..models.trade import RecentTrade
from ..transport.http import HttpTransport
from .numbers import finite_decimal

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
        if not symbol:
            raise ValueError("symbol must not be empty")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("limit must be a positive integer")
        params: dict[str, object] = {"symbol": symbol}
        if limit is not None:
            params["limit"] = limit
        response = await self._transport.get("/api/query_recent_trades", params=params)
        return _recent_trade_payload(response)

    async def recent_trades(
        self, symbol: str, *, limit: int | None = None
    ) -> list[RecentTrade]:
        values = await self._recent_trades_raw(symbol, limit=limit)
        return _protocol_decode(
            "query_recent_trades",
            lambda: [
                RecentTrade(
                    symbol=str(value["symbol"]),
                    price=finite_decimal(value["price"]),
                    qty=finite_decimal(value["qty"]),
                    quote_qty=finite_decimal(value["quote_qty"]),
                    is_buyer_taker=_required_bool(value["is_buyer_taker"]),
                    time=value.get("time") if isinstance(value.get("time"), str) else None,
                )
                for value in values
            ],
        )

    async def recent_trade_snapshots(
        self, symbol: str, *, limit: int | None = None
    ) -> list[RecentTrade]:
        return await self.recent_trades(symbol, limit=limit)

    async def server_time(self) -> int:
        value = await self._transport.get("/api/kline/time")
        return _protocol_decode("kline_time", lambda: _server_time(value))

    async def kline_history(
        self,
        symbol: str,
        from_time: int,
        to_time: int,
        resolution: KlineResolution | str,
        *,
        countback: int | None = None,
    ) -> KlineHistory:
        resolution_value = _kline_parameters(
            symbol, from_time, to_time, resolution, countback
        )
        response = await self._transport.get(
            "/api/kline/history",
            params={
                "symbol": symbol,
                "from": from_time,
                "to": to_time,
                "resolution": resolution_value,
                **({"countback": countback} if countback is not None else {}),
            },
        )
        return _protocol_decode("kline_history", lambda: _kline_history(response))

    async def health(self) -> str:
        value = await self._transport.get_text("/api/health")
        if value != "OK":
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "malformed response from health",
                retryable=False,
            )
        return value


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
        min_order_qty=finite_decimal(value["min_order_qty"]),
        max_order_qty=finite_decimal(value["max_order_qty"]),
        max_position_size=finite_decimal(value["max_position_size"]),
        max_leverage=int(value["max_leverage"]),
        def_leverage=int(value["def_leverage"]),
        max_open_orders=int(value["max_open_orders"]),
        price_cap_ratio=finite_decimal(value["price_cap_ratio"]),
        price_floor_ratio=finite_decimal(value["price_floor_ratio"]),
        maker_fee=finite_decimal(value["maker_fee"]),
        taker_fee=finite_decimal(value["taker_fee"]),
        depth_ticks=tuple(finite_decimal(item) for item in str(value["depth_ticks"]).split(",")),
        enabled=value.get("enabled") if isinstance(value.get("enabled"), bool) else None,
        created_at=value.get("created_at") if isinstance(value.get("created_at"), str) else None,
        updated_at=value.get("updated_at") if isinstance(value.get("updated_at"), str) else None,
    )


def _server_time(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError("server time must be a non-negative JSON integer")
    return value


def _recent_trade_payload(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("result")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise StandXError(
            ErrorCode.PROTOCOL_ERROR,
            "recent trade response must be a list or contain a result list",
            retryable=False,
        )
    return cast(list[dict[str, Any]], value)


def _required_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected JSON boolean")
    return value


def _kline_parameters(
    symbol: str,
    from_time: int,
    to_time: int,
    resolution: KlineResolution | str,
    countback: int | None,
) -> str:
    if not symbol:
        raise ValueError("symbol must not be empty")
    if isinstance(from_time, bool) or not isinstance(from_time, int) or from_time < 0:
        raise ValueError("from_time must be a non-negative integer")
    if isinstance(to_time, bool) or not isinstance(to_time, int) or to_time <= from_time:
        raise ValueError("to_time must be greater than from_time")
    resolution_value = resolution.value if isinstance(resolution, KlineResolution) else resolution
    if resolution_value not in {item.value for item in KlineResolution}:
        raise ValueError("unsupported kline resolution")
    if countback is not None and (
        isinstance(countback, bool) or not isinstance(countback, int) or countback <= 0
    ):
        raise ValueError("countback must be a positive integer")
    return resolution_value


def _kline_history(value: object) -> KlineHistory:
    if not isinstance(value, dict) or value.get("s") != "ok":
        raise TypeError("kline response status was not ok")
    arrays = [value[key] for key in ("t", "c", "o", "h", "l", "v")]
    if not all(isinstance(array, list) for array in arrays):
        raise TypeError("kline response arrays are malformed")
    if len({len(array) for array in arrays}) != 1:
        raise ValueError("kline response arrays have different lengths")
    bars = tuple(
        KlineBar(
            time=_server_time(timestamp),
            close=finite_decimal(close),
            open=finite_decimal(open_price),
            high=finite_decimal(high),
            low=finite_decimal(low),
            volume=finite_decimal(volume),
        )
        for timestamp, close, open_price, high, low, volume in zip(*arrays, strict=True)
    )
    return KlineHistory(status="ok", bars=bars)


def _market_overview(response: dict[str, Any]) -> MarketOverview:
    summary = response["summary"]
    return MarketOverview(
        open_interest_notional=finite_decimal(summary["open_interest_notional"]),
        symbol_count=int(summary["symbol_count"]),
        volume_quote_24h=finite_decimal(summary["volume_quote_24h"]),
        symbols=tuple(_overview_symbol(value) for value in response["symbols"]),
    )


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else finite_decimal(value)


def _levels(value: Any) -> tuple[tuple[Decimal, Decimal], ...]:
    return tuple((finite_decimal(level[0]), finite_decimal(level[1])) for level in value)


def _spread(value: Any) -> tuple[Decimal, Decimal] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    return finite_decimal(value[0]), finite_decimal(value[1])


def _overview_symbol(value: dict[str, Any]) -> MarketOverviewSymbol:
    return MarketOverviewSymbol(
        base=str(value["base"]),
        quote=str(value["quote"]),
        symbol=str(value["symbol"]),
        last_price=finite_decimal(value["last_price"]),
        mark_price=finite_decimal(value["mark_price"]),
        funding_rate=finite_decimal(value["funding_rate"]),
        open_interest=finite_decimal(value["open_interest"]),
        open_interest_notional=finite_decimal(value["open_interest_notional"]),
        price_change_pct=float(value["price_change_pct"]),
        volume_24h=finite_decimal(value["volume_24h"]),
        volume_quote_24h=finite_decimal(value["volume_quote_24h"]),
        time=str(value["time"]),
    )


def _symbol_market(value: dict[str, Any]) -> SymbolMarket:
    return SymbolMarket(
        symbol=str(value["symbol"]),
        last_price=_optional_decimal(value.get("last_price")),
        funding_rate=finite_decimal(value["funding_rate"]),
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
