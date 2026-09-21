"""WebSocket transport shared by the two documented StandX streams."""

from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection


class WebSocketTransport:
    def __init__(
        self,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        ping_interval: float | None = 20.0,
        ping_timeout: float | None = 60.0,
    ) -> None:
        if ping_interval is not None and ping_interval <= 0:
            raise ValueError("ping_interval must be positive or None")
        if ping_timeout is not None and ping_timeout <= 0:
            raise ValueError("ping_timeout must be positive or None")
        self.endpoint = endpoint
        self.headers = headers or {}
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.connection: ClientConnection | None = None

    async def connect(self) -> ClientConnection:
        self.connection = await websockets.connect(
            self.endpoint,
            additional_headers=self.headers,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
        )
        return self.connection

    async def send(self, message: str) -> None:
        if self.connection is None:
            raise RuntimeError("WebSocket is not connected")
        await self.connection.send(message)

    async def receive(self) -> Any:
        if self.connection is None:
            raise RuntimeError("WebSocket is not connected")
        return await self.connection.recv()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None
