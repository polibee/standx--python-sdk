"""StandX asynchronous order response stream envelopes."""

import json
from typing import Any

from ..transport.websocket import WebSocketTransport
from .base import StreamBase


class OrderResponseStream(StreamBase):
    def __init__(
        self, endpoint: str, *, session_id: str, transport: WebSocketTransport | None = None
    ) -> None:
        super().__init__(endpoint)
        if not session_id:
            raise ValueError("session_id must not be empty")
        self.session_id = session_id
        self.transport = transport or WebSocketTransport(endpoint)

    def request(self, method: str, params: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        if method not in {"auth:login", "order:new", "order:cancel"}:
            raise ValueError("unsupported StandX Order Response method")
        return {
            "session_id": self.session_id,
            "request_id": request_id,
            "method": method,
            "header": {},
            "params": json.dumps(params, separators=(",", ":"), ensure_ascii=False),
        }

    async def connect(self) -> None:
        await self.transport.connect()

    async def send_request(self, method: str, params: dict[str, Any], *, request_id: str) -> None:
        await self.transport.send(
            json.dumps(self.request(method, params, request_id=request_id), separators=(",", ":"))
        )

    async def receive(self) -> Any:
        return json.loads(await self.transport.receive())

    async def close_async(self) -> None:
        self.close()
        await self.transport.close()
