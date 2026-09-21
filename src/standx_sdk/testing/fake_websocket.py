"""Deterministic in-memory WebSocket server and transport."""

import asyncio
import json
from typing import Any


class FakeWebSocketTransport:
    def __init__(self) -> None:
        self._server_to_client: asyncio.Queue[str] = asyncio.Queue()
        self._client_to_server: asyncio.Queue[str] = asyncio.Queue()
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def send(self, message: str) -> None:
        if not self.connected:
            raise ConnectionError("fake websocket is not connected")
        await self._client_to_server.put(message)

    async def receive(self) -> str:
        if not self.connected:
            raise ConnectionError("fake websocket is not connected")
        return await self._server_to_client.get()

    async def close(self) -> None:
        self.connected = False


class FakeWebSocketServer:
    """In-memory peer used to test stream protocol behavior without a network."""

    def __init__(self) -> None:
        self.transport = FakeWebSocketTransport()

    async def send_to_client(self, payload: dict[str, Any] | str) -> None:
        message = payload if isinstance(payload, str) else json.dumps(payload)
        await self.transport._server_to_client.put(message)

    async def receive_from_client(self) -> dict[str, Any]:
        message = await self.transport._client_to_server.get()
        value = json.loads(message)
        if not isinstance(value, dict):
            raise TypeError("fake websocket message must be an object")
        return value
