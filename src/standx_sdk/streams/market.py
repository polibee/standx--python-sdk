"""StandX Market Stream envelope, DTO mapping, and lifecycle boundary."""

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any

from ..errors import ErrorCode, StandXError
from ..models.stream import (
    BalanceEvent,
    DepthBookEvent,
    PositionEvent,
    PriceEvent,
    PublicTradeEvent,
    UserOrderEvent,
    UserTradeEvent,
)
from ..transport.websocket import WebSocketTransport
from .base import StreamBase


class MarketStream(StreamBase):
    def __init__(self, endpoint: str, transport: WebSocketTransport | None = None) -> None:
        super().__init__(endpoint)
        self.transport = transport or WebSocketTransport(endpoint)
        self._subscriptions: list[tuple[str, str | None]] = []
        self._authenticated = False
        self._auth_token: str | None = None
        self._impersonate: str | None = None

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def subscription(self, channel: str, symbol: str | None = None) -> dict[str, Any]:
        if channel in {"price", "depth_book", "public_trade"} and not symbol:
            raise ValueError(f"{channel} subscription requires symbol")
        if channel not in {
            "price",
            "depth_book",
            "public_trade",
            "order",
            "position",
            "balance",
            "trade",
        }:
            raise ValueError("unsupported StandX Market Stream channel")
        value: dict[str, str] = {"channel": channel}
        if symbol is not None:
            value["symbol"] = symbol
        return {"subscribe": value}

    async def connect(self) -> None:
        if self.closed:
            raise RuntimeError("closed stream cannot connect")
        await self.transport.connect()

    async def connect_with_backoff(
        self,
        *,
        max_attempts: int = 5,
        initial_delay: float = 0.5,
        max_delay: float | None = None,
        jitter: Callable[[float], float] | None = None,
        sleep: Callable[[float], object] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if initial_delay < 0:
            raise ValueError("initial_delay must not be negative")
        if max_delay is not None and max_delay <= 0:
            raise ValueError("max_delay must be positive or None")
        pause = sleep or asyncio.sleep
        delay = initial_delay
        for attempt in range(max_attempts):
            try:
                await self.connect()
                return
            except Exception:
                if attempt == max_attempts - 1:
                    raise
                wait = delay if max_delay is None else min(delay, max_delay)
                if jitter is not None:
                    wait = jitter(wait)
                if max_delay is not None:
                    wait = min(wait, max_delay)
                if wait < 0:
                    raise ValueError("jitter must not return a negative delay")
                result = pause(wait)
                if inspect.isawaitable(result):
                    await result
                delay *= 2

    async def subscribe(self, channel: str, symbol: str | None = None) -> None:
        if channel in {"order", "position", "balance", "trade"} and not self.authenticated:
            raise RuntimeError("authenticate before subscribing to user channels")
        subscription = (channel, symbol)
        if subscription not in self._subscriptions:
            self._subscriptions.append(subscription)
        await self.transport.send(
            json.dumps(self.subscription(channel, symbol), separators=(",", ":"))
        )

    async def authenticate(
        self,
        token: str,
        *,
        impersonate: str | None = None,
        streams: list[str] | None = None,
    ) -> None:
        if not token:
            raise ValueError("token must not be empty")
        auth: dict[str, Any] = {"token": token}
        if impersonate is not None:
            auth["impersonate"] = impersonate
        if streams is not None:
            auth["streams"] = [{"channel": channel} for channel in streams]
        await self.transport.send(json.dumps({"auth": auth}, separators=(",", ":")))
        response = json.loads(await self.transport.receive())
        if (
            not isinstance(response, dict)
            or response.get("channel") != "auth"
            or not isinstance(response.get("data"), dict)
            or response["data"].get("code") != 200
        ):
            raise RuntimeError("Market Stream authentication failed")
        self._authenticated = True
        self._auth_token = token
        self._impersonate = impersonate

    async def reconnect(self) -> None:
        if self.closed:
            raise RuntimeError("closed stream cannot reconnect")
        await self.transport.close()
        await self.connect()
        if self._auth_token is not None:
            await self.authenticate(self._auth_token, impersonate=self._impersonate)
        for channel, symbol in self._subscriptions:
            try:
                await self.subscribe(channel, symbol)
            except Exception as exc:
                target = channel if symbol is None else f"{channel}:{symbol}"
                raise StandXError(
                    ErrorCode.WS_RESUBSCRIBE_FAILED,
                    f"failed to restore subscription {target}",
                    retryable=True,
                ) from exc

    async def receive(self) -> Any:
        try:
            return json.loads(await self.transport.receive())
        except (json.JSONDecodeError, TypeError) as exc:
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "invalid JSON from Market Stream",
            ) from exc

    def decode(self, message: dict[str, Any]) -> Any:
        channel = message.get("channel")
        data = message.get("data")
        if not isinstance(channel, str) or not isinstance(data, dict):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "invalid StandX Market Stream message",
            )
        if channel == "order":
            return UserOrderEvent(
                id=int(data["id"]),
                status=str(data["status"]),
                qty=_decimal(data["qty"]),
                symbol=_optional_str(data.get("symbol")),
                side=_optional_str(data.get("side")),
                order_type=_optional_str(data.get("order_type")),
                price=_optional_decimal(data.get("price")),
                fill_qty=_optional_decimal(data.get("fill_qty")),
                fill_avg_price=_optional_decimal(data.get("fill_avg_price")),
                cl_ord_id=_optional_str(data.get("cl_ord_id")),
                reduce_only=bool(data.get("reduce_only", False)),
                time_in_force=_optional_str(data.get("time_in_force")),
                avail_locked=_optional_decimal(data.get("avail_locked")),
                closed_block=_optional_int(data.get("closed_block")),
                created_at=_optional_str(data.get("created_at")),
                created_block=_optional_int(data.get("created_block")),
                leverage=_optional_int(data.get("leverage")),
                liq_id=_optional_int(data.get("liq_id")),
                margin=_optional_decimal(data.get("margin")),
                payload=data.get("payload"),
                position_id=_optional_int(data.get("position_id")),
                remark=_optional_str(data.get("remark")),
                source=_optional_str(data.get("source")),
                user=_optional_str(data.get("user")),
                updated_at=_optional_str(data.get("updated_at")),
            )
        if channel == "position":
            return PositionEvent(
                id=int(data["id"]),
                qty=_decimal(data["qty"]),
                leverage=int(data["leverage"]),
                symbol=_optional_str(data.get("symbol")),
                entry_price=_optional_decimal(data.get("entry_price")),
                entry_value=_optional_decimal(data.get("entry_value")),
                created_at=_optional_str(data.get("created_at")),
                initial_margin=_optional_decimal(data.get("initial_margin")),
                margin_asset=_optional_str(data.get("margin_asset")),
                margin_mode=_optional_str(data.get("margin_mode")),
                realized_pnl=_optional_decimal(data.get("realized_pnl")),
                status=_optional_str(data.get("status")),
                user=_optional_str(data.get("user")),
                updated_at=_optional_str(data.get("updated_at")),
            )
        if channel == "balance":
            return BalanceEvent(
                token=str(data["token"]),
                total=_decimal(data["total"]),
                free=_optional_decimal(data.get("free")),
                locked=_optional_decimal(data.get("locked")),
                occupied=_optional_decimal(data.get("occupied")),
                account_type=_optional_str(data.get("account_type")),
                created_at=_optional_str(data.get("created_at")),
                id=_optional_str(data.get("id")),
                inbound=_optional_decimal(data.get("inbound")),
                is_enabled=data.get("is_enabled") if isinstance(data.get("is_enabled"), bool) else None,
                kind=_optional_str(data.get("kind")),
                last_tx=_optional_str(data.get("last_tx")),
                last_tx_updated_at=_optional_int(data.get("last_tx_updated_at")),
                outbound=_optional_decimal(data.get("outbound")),
                ref_id=_optional_int(data.get("ref_id")),
                updated_at=_optional_str(data.get("updated_at")),
                version=_optional_int(data.get("version")),
                wallet_id=_optional_str(data.get("wallet_id")),
            )
        if channel == "trade":
            return UserTradeEvent(
                id=int(data["id"]),
                symbol=str(data["symbol"]),
                qty=_decimal(data["qty"]),
                price=_decimal(data["price"]),
                order_id=_optional_int(data.get("order_id")),
                fee_qty=_optional_decimal(data.get("fee_qty")),
                fee_asset=_optional_str(data.get("fee_asset")),
            )
        if channel == "price":
            spread = data.get("spread")
            return PriceEvent(
                symbol=str(data["symbol"]),
                last_price=_decimal(data["last_price"]),
                mark_price=_optional_decimal(data.get("mark_price")),
                index_price=_optional_decimal(data.get("index_price")),
                mid_price=_optional_decimal(data.get("mid_price")),
                spread=None
                if spread is None
                else (_decimal(spread[0]), _decimal(spread[1])),
            )
        if channel == "depth_book":
            return DepthBookEvent(
                symbol=str(data["symbol"]),
                asks=_levels(data.get("asks", [])),
                bids=_levels(data.get("bids", [])),
            )
        if channel == "public_trade":
            return PublicTradeEvent(
                id=int(data["id"]),
                symbol=str(data["symbol"]),
                price=_decimal(data["price"]),
                qty=_decimal(data["qty"]),
                side=_optional_str(data.get("side")),
            )
        raise ValueError(f"unsupported StandX Market Stream channel: {channel}")

    async def close_async(self) -> None:
        self.close()
        self._authenticated = False
        await self.transport.close()


def _decimal(value: Any) -> Any:
    from decimal import Decimal

    return Decimal(str(value))


def _optional_decimal(value: Any) -> Any:
    return None if value is None else _decimal(value)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _levels(value: Any) -> tuple[tuple[Any, Any], ...]:
    return tuple((_decimal(level[0]), _decimal(level[1])) for level in value)
