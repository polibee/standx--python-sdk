from decimal import Decimal
from typing import Any, cast

from ..models.account import BalanceSnapshot, PositionSnapshot
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

    async def change_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        return cast(dict[str, Any], await self._transport.post(
            "/api/change_leverage", json={"symbol": symbol, "leverage": leverage}, signed=True
        ))

    async def change_margin_mode(self, symbol: str, margin_mode: str) -> dict[str, Any]:
        if margin_mode not in {"cross", "isolated"}:
            raise ValueError("margin_mode must be cross or isolated")
        return cast(dict[str, Any], await self._transport.post(
            "/api/change_margin_mode",
            json={"symbol": symbol, "margin_mode": margin_mode},
            signed=True,
        ))

    async def trades(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return cast(list[dict[str, Any]], _decimalize(await self._transport.get("/api/query_trades", params=params)))

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
