from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar, cast

from ..errors import ErrorCode, StandXError
from ..models.account import BalanceSnapshot, PositionSnapshot
from ..models.account_config import ConfigChangeResult, PositionConfig
from ..models.order import MarginMode
from ..models.trade import FundingPayment, FundingRate, UserTrade
from ..transport.http import HttpTransport
from .numbers import finite_decimal

_T = TypeVar("_T")


def _decimalize(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (ArithmeticError, ValueError):
            return value
    if isinstance(value, dict):
        return {key: _decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    return value


class AccountApi:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def _balance_raw(self) -> dict[str, Any]:
        return cast(dict[str, Any], _decimalize(await self._transport.get("/api/query_balance")))

    async def balance(self) -> BalanceSnapshot:
        value = await self._balance_raw()
        return _protocol_decode("query_balance", lambda: _balance_from(value))

    async def balance_snapshot(self) -> BalanceSnapshot:
        return await self.balance()

    async def _positions_raw(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        response = _decimalize(await self._transport.get("/api/query_positions", params=params))
        if isinstance(response, dict):
            return cast(list[dict[str, Any]], response.get("result", []))
        return cast(list[dict[str, Any]], response)

    async def positions(self, symbol: str | None = None) -> list[PositionSnapshot]:
        values = await self._positions_raw(symbol)
        return _protocol_decode("query_positions", lambda: _positions_from(values))

    async def position_snapshots(self, symbol: str | None = None) -> list[PositionSnapshot]:
        return await self.positions(symbol)

    async def _position_config_raw(self, symbol: str) -> dict[str, Any]:
        return cast(dict[str, Any], _decimalize(
            await self._transport.get("/api/query_position_config", params={"symbol": symbol})
        ))

    async def position_config(self, symbol: str) -> PositionConfig:
        value = await self._position_config_raw(symbol)
        return _protocol_decode(
            "query_position_config",
            lambda: PositionConfig(
                symbol=str(value["symbol"]),
                leverage=int(value["leverage"]),
                margin_mode=MarginMode(str(value["margin_mode"])),
            ),
        )

    async def position_config_snapshot(self, symbol: str) -> PositionConfig:
        return await self.position_config(symbol)

    async def _change_leverage_raw(self, symbol: str, leverage: int) -> dict[str, Any]:
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        return cast(dict[str, Any], await self._transport.post(
            "/api/change_leverage", json={"symbol": symbol, "leverage": leverage}, signed=True
        ))

    async def change_leverage(self, symbol: str, leverage: int) -> ConfigChangeResult:
        value = await self._change_leverage_raw(symbol, leverage)
        return _protocol_decode("change_leverage", lambda: _config_change(value))

    async def change_leverage_config(self, symbol: str, leverage: int) -> ConfigChangeResult:
        return await self.change_leverage(symbol, leverage)

    async def _change_margin_mode_raw(self, symbol: str, margin_mode: str) -> dict[str, Any]:
        if margin_mode not in {"cross", "isolated"}:
            raise ValueError("margin_mode must be cross or isolated")
        return cast(dict[str, Any], await self._transport.post(
            "/api/change_margin_mode",
            json={"symbol": symbol, "margin_mode": margin_mode},
            signed=True,
        ))

    async def change_margin_mode(
        self, symbol: str, margin_mode: MarginMode
    ) -> ConfigChangeResult:
        value = await self._change_margin_mode_raw(symbol, margin_mode.value)
        return _protocol_decode("change_margin_mode", lambda: _config_change(value))

    async def change_margin_mode_config(
        self, symbol: str, margin_mode: MarginMode
    ) -> ConfigChangeResult:
        return await self.change_margin_mode(symbol, margin_mode)

    async def _trades_raw(
        self,
        symbol: str | None = None,
        *,
        last_id: int | None = None,
        side: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params = _history_params(
            symbol=symbol, last_id=last_id, side=side, start=start, end=end, limit=limit
        )
        response = _decimalize(await self._transport.get("/api/query_trades", params=params))
        if isinstance(response, dict):
            return cast(list[dict[str, Any]], response.get("result", []))
        return cast(list[dict[str, Any]], response)

    async def trades(
        self,
        symbol: str | None = None,
        *,
        last_id: int | None = None,
        side: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> list[UserTrade]:
        values = await self._trades_raw(
            symbol, last_id=last_id, side=side, start=start, end=end, limit=limit
        )
        return _protocol_decode("query_trades", lambda: [_trade_from(value) for value in values])

    async def trade_snapshots(
        self,
        symbol: str | None = None,
        *,
        last_id: int | None = None,
        side: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> list[UserTrade]:
        return await self.trades(
            symbol, last_id=last_id, side=side, start=start, end=end, limit=limit
        )

    async def funding_history(
        self,
        symbol: str | None = None,
        *,
        start: str | None = None,
        end: str | None = None,
        last_id: int | None = None,
        limit: int | None = None,
    ) -> list[FundingPayment]:
        params = _history_params(
            symbol=symbol, start=start, end=end, last_id=last_id, limit=limit
        )
        response = _decimalize(
            await self._transport.get("/api/query_funding_history", params=params)
        )
        values = response.get("result", response) if isinstance(response, dict) else response
        return _protocol_decode(
            "query_funding_history", lambda: [_funding_from(value) for value in values]
        )

    async def _funding_rates_raw(
        self, symbol: str, start_time: int, end_time: int
    ) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], _decimalize(
            await self._transport.get(
                "/api/query_funding_rates",
                params={"symbol": symbol, "start_time": start_time, "end_time": end_time},
            )
        ))

    async def funding_rates(
        self, symbol: str, start_time: int, end_time: int
    ) -> list[FundingRate]:
        values = await self._funding_rates_raw(symbol, start_time, end_time)
        return _protocol_decode(
            "query_funding_rates", lambda: [_funding_rate_from(value) for value in values]
        )

    async def funding_rate_snapshots(
        self, symbol: str, start_time: int, end_time: int
    ) -> list[FundingRate]:
        return await self.funding_rates(symbol, start_time, end_time)


__all__ = ["AccountApi"]


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


def _positions_from(values: list[dict[str, Any]]) -> list[PositionSnapshot]:
    return [
        PositionSnapshot(
            id=int(value["id"]),
            symbol=str(value["symbol"]),
            qty=_required_decimal(value, "qty"),
            leverage=int(value["leverage"]),
            bankruptcy_price=_optional_decimal(value.get("bankruptcy_price")),
            created_at=_optional_string(value.get("created_at")),
            entry_price=_optional_decimal(value.get("entry_price")),
            entry_value=_optional_decimal(value.get("entry_value")),
            holding_margin=_optional_decimal(value.get("holding_margin")),
            initial_margin=_optional_decimal(value.get("initial_margin")),
            liq_price=_optional_decimal(value.get("liq_price")),
            maint_margin=_optional_decimal(value.get("maint_margin")),
            margin_asset=_optional_string(value.get("margin_asset")),
            margin_mode=_optional_string(value.get("margin_mode")),
            mark_price=_optional_decimal(value.get("mark_price")),
            mmr=_optional_decimal(value.get("mmr")),
            position_value=_optional_decimal(value.get("position_value")),
            status=_optional_string(value.get("status")),
            realized_pnl=_optional_decimal(value.get("realized_pnl")),
            upnl=_optional_decimal(value.get("upnl")),
            time=_optional_string(value.get("time")),
            updated_at=_optional_string(value.get("updated_at")),
        )
        for value in values
    ]


def _required_decimal(value: dict[str, Any], key: str) -> Decimal:
    if key not in value:
        raise ValueError(f"StandX response missing {key}")
    return finite_decimal(value[key])


def _balance_from(value: dict[str, Any]) -> BalanceSnapshot:
    return BalanceSnapshot(
        balance=_required_decimal(value, "balance"),
        equity=_required_decimal(value, "equity"),
        upnl=_required_decimal(value, "upnl"),
        isolated_balance=_optional_decimal(value.get("isolated_balance")),
        isolated_upnl=_optional_decimal(value.get("isolated_upnl")),
        cross_balance=_optional_decimal(value.get("cross_balance")),
        cross_margin=_optional_decimal(value.get("cross_margin")),
        cross_upnl=_optional_decimal(value.get("cross_upnl")),
        locked=_optional_decimal(value.get("locked")),
        cross_available=_optional_decimal(value.get("cross_available")),
        pnl_freeze=_optional_decimal(value.get("pnl_freeze")),
    )


def _history_params(**values: object) -> dict[str, object] | None:
    params = {key: value for key, value in values.items() if value is not None}
    return params or None


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else finite_decimal(value)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _trade_from(value: dict[str, Any]) -> UserTrade:
    return UserTrade(
        id=int(value["id"]),
        order_id=int(value["order_id"]),
        symbol=str(value["symbol"]),
        side=str(value["side"]),
        price=finite_decimal(value["price"]),
        qty=finite_decimal(value["qty"]),
        value=finite_decimal(value["value"]),
        fee_asset=str(value["fee_asset"]),
        fee_qty=finite_decimal(value["fee_qty"]),
        pnl=finite_decimal(value["pnl"]),
        created_at=_optional_string(value.get("created_at")),
        updated_at=_optional_string(value.get("updated_at")),
    )


def _funding_from(value: dict[str, Any]) -> FundingPayment:
    return FundingPayment(
        id=int(value["id"]),
        asset=str(value["asset"]),
        symbol=str(value["symbol"]),
        qty=finite_decimal(value["qty"]),
        txn_type=str(value["txn_type"]),
        transact_time=str(value["transact_time"]),
        created_at=_optional_string(value.get("created_at")),
        updated_at=_optional_string(value.get("updated_at")),
    )


def _funding_rate_from(value: dict[str, Any]) -> FundingRate:
    return FundingRate(
        id=int(value["id"]),
        symbol=str(value["symbol"]),
        funding_rate=finite_decimal(value["funding_rate"]),
        index_price=finite_decimal(value["index_price"]),
        mark_price=finite_decimal(value["mark_price"]),
        premium=finite_decimal(value["premium"]),
        time=_optional_string(value.get("time")),
        created_at=_optional_string(value.get("created_at")),
        updated_at=_optional_string(value.get("updated_at")),
    )


def _config_change(value: dict[str, Any]) -> ConfigChangeResult:
    return ConfigChangeResult(
        code=int(value["code"]),
        message=str(value["message"]),
        request_id=str(value["request_id"]),
    )
