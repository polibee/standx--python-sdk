from decimal import Decimal
from typing import Any, cast

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
        return cast(list[dict[str, Any]], _decimalize(await self._transport.get("/api/query_positions", params=params)))

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
