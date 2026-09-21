"""Typed position and trade service views for the public client facade."""

import builtins

from ..models.account import PositionSnapshot
from ..models.account_config import ConfigChangeResult, PositionConfig
from ..models.order import MarginMode
from ..models.trade import FundingPayment, FundingRate, UserTrade
from .account import AccountApi


class PositionsApi:
    """Position-focused view over the shared account service."""

    def __init__(self, account: AccountApi) -> None:
        self._account = account

    async def list(self, symbol: str | None = None) -> list[PositionSnapshot]:
        return await self._account.positions(symbol)

    async def config(self, symbol: str) -> PositionConfig:
        return await self._account.position_config(symbol)

    async def change_leverage(self, symbol: str, leverage: int) -> ConfigChangeResult:
        return await self._account.change_leverage(symbol, leverage)

    async def change_margin_mode(
        self, symbol: str, margin_mode: MarginMode
    ) -> ConfigChangeResult:
        return await self._account.change_margin_mode(symbol, margin_mode)


class TradesApi:
    """User trade and funding-history view over the shared account service."""

    def __init__(self, account: AccountApi) -> None:
        self._account = account

    async def list(
        self,
        symbol: str | None = None,
        *,
        last_id: int | None = None,
        side: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[UserTrade]:
        return await self._account.trades(
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
    ) -> builtins.list[FundingPayment]:
        return await self._account.funding_history(
            symbol, start=start, end=end, last_id=last_id, limit=limit
        )

    async def funding_rates(
        self, symbol: str, start_time: int, end_time: int
    ) -> builtins.list[FundingRate]:
        return await self._account.funding_rates(symbol, start_time, end_time)


__all__ = ["PositionsApi", "TradesApi"]
