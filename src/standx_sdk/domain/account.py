from decimal import Decimal
from typing import Any, cast

from ..models.account import BalanceSnapshot, PositionSnapshot
from ..models.account_config import ConfigChangeResult, PositionConfig
from ..models.order import MarginMode
from ..models.trade import FundingPayment, UserTrade
from ..transport.http import HttpTransport


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

    async def balance(self) -> dict[str, Any]:
        return cast(dict[str, Any], _decimalize(await self._transport.get("/api/query_balance")))

    async def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        response = _decimalize(await self._transport.get("/api/query_positions", params=params))
        if isinstance(response, dict):
            return cast(list[dict[str, Any]], response.get("result", []))
        return cast(list[dict[str, Any]], response)

    async def balance_snapshot(self) -> BalanceSnapshot:
        value = await self.balance()
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

    async def position_snapshots(self, symbol: str | None = None) -> list[PositionSnapshot]:
        values = await self.positions(symbol)
        return [
            PositionSnapshot(
                id=int(value["id"]),
                symbol=str(value["symbol"]),
                qty=_required_decimal(value, "qty"),
                leverage=int(value["leverage"]),
                entry_price=_optional_decimal(value.get("entry_price")),
                entry_value=_optional_decimal(value.get("entry_value")),
                margin_mode=_optional_string(value.get("margin_mode")),
                status=_optional_string(value.get("status")),
                realized_pnl=_optional_decimal(value.get("realized_pnl")),
                upnl=_optional_decimal(value.get("upnl")),
                updated_at=_optional_string(value.get("updated_at")),
            )
            for value in values
        ]

    async def position_config(self, symbol: str) -> dict[str, Any]:
        return cast(dict[str, Any], _decimalize(
            await self._transport.get("/api/query_position_config", params={"symbol": symbol})
        ))

    async def position_config_snapshot(self, symbol: str) -> PositionConfig:
        value = await self.position_config(symbol)
        return PositionConfig(
            symbol=str(value["symbol"]),
            leverage=int(value["leverage"]),
            margin_mode=MarginMode(str(value["margin_mode"])),
        )

    async def change_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        return cast(dict[str, Any], await self._transport.post(
            "/api/change_leverage", json={"symbol": symbol, "leverage": leverage}, signed=True
        ))

    async def change_leverage_config(self, symbol: str, leverage: int) -> ConfigChangeResult:
        return _config_change(await self.change_leverage(symbol, leverage))

    async def change_margin_mode(self, symbol: str, margin_mode: str) -> dict[str, Any]:
        if margin_mode not in {"cross", "isolated"}:
            raise ValueError("margin_mode must be cross or isolated")
        return cast(dict[str, Any], await self._transport.post(
            "/api/change_margin_mode",
            json={"symbol": symbol, "margin_mode": margin_mode},
            signed=True,
        ))

    async def change_margin_mode_config(
        self, symbol: str, margin_mode: MarginMode
    ) -> ConfigChangeResult:
        return _config_change(await self.change_margin_mode(symbol, margin_mode.value))

    async def trades(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        response = _decimalize(await self._transport.get("/api/query_trades", params=params))
        if isinstance(response, dict):
            return cast(list[dict[str, Any]], response.get("result", []))
        return cast(list[dict[str, Any]], response)

    async def trade_snapshots(self, symbol: str | None = None) -> list[UserTrade]:
        values = await self.trades(symbol)
        return [_trade_from(value) for value in values]

    async def funding_history(self, symbol: str | None = None) -> list[FundingPayment]:
        params = {"symbol": symbol} if symbol else None
        response = _decimalize(
            await self._transport.get("/api/query_funding_history", params=params)
        )
        values = response.get("result", response) if isinstance(response, dict) else response
        return [_funding_from(value) for value in values]

    async def funding_rates(
        self, symbol: str, start_time: int, end_time: int
    ) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], _decimalize(
            await self._transport.get(
                "/api/query_funding_rates",
                params={"symbol": symbol, "start_time": start_time, "end_time": end_time},
            )
        ))


__all__ = ["AccountApi"]


def _required_decimal(value: dict[str, Any], key: str) -> Decimal:
    if key not in value:
        raise ValueError(f"StandX response missing {key}")
    return Decimal(str(value[key]))


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _trade_from(value: dict[str, Any]) -> UserTrade:
    return UserTrade(
        id=int(value["id"]),
        order_id=int(value["order_id"]),
        symbol=str(value["symbol"]),
        side=str(value["side"]),
        price=Decimal(str(value["price"])),
        qty=Decimal(str(value["qty"])),
        value=Decimal(str(value["value"])),
        fee_asset=str(value["fee_asset"]),
        fee_qty=Decimal(str(value["fee_qty"])),
        pnl=Decimal(str(value["pnl"])),
        created_at=_optional_string(value.get("created_at")),
        updated_at=_optional_string(value.get("updated_at")),
    )


def _funding_from(value: dict[str, Any]) -> FundingPayment:
    return FundingPayment(
        id=int(value["id"]),
        asset=str(value["asset"]),
        symbol=str(value["symbol"]),
        qty=Decimal(str(value["qty"])),
        txn_type=str(value["txn_type"]),
        transact_time=str(value["transact_time"]),
        created_at=_optional_string(value.get("created_at")),
        updated_at=_optional_string(value.get("updated_at")),
    )


def _config_change(value: dict[str, Any]) -> ConfigChangeResult:
    return ConfigChangeResult(
        code=int(value["code"]),
        message=str(value["message"]),
        request_id=str(value["request_id"]),
    )
