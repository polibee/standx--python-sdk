"""WebSocket transport shared by the two documented StandX streams."""

from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection


class WebSocketTransport:
    def __init__(self, endpoint: str, *, headers: dict[str, str] | None = None) -> None:
        self.endpoint = endpoint
        self.headers = headers or {}
        self.connection: ClientConnection | None = None

    async def connect(self) -> ClientConnection:
        self.connection = await websockets.connect(self.endpoint, additional_headers=self.headers)
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
