"""StandX Market Stream envelope and subscription boundary."""

from typing import Any

from ..transport.websocket import WebSocketTransport
from .base import StreamBase


class MarketStream(StreamBase):
    def __init__(self, endpoint: str, transport: WebSocketTransport | None = None) -> None:
        super().__init__(endpoint)
        self.transport = transport or WebSocketTransport(endpoint)

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
        await self.transport.connect()

    async def subscribe(self, channel: str, symbol: str | None = None) -> None:
        import json

        await self.transport.send(
            json.dumps(self.subscription(channel, symbol), separators=(",", ":"))
        )

    async def receive(self) -> Any:
        import json

        return json.loads(await self.transport.receive())

    async def close_async(self) -> None:
        self.close()
        await self.transport.close()
