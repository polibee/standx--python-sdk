"""StandX asynchronous order response stream envelopes."""

import json
from collections.abc import Awaitable, Callable
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
        self._pending_request_ids: set[str] = set()
        self._pending_requests: dict[str, dict[str, Any]] = {}

    @property
    def pending_request_ids(self) -> set[str]:
        return set(self._pending_request_ids)

    def request(self, method: str, params: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        if method not in {"auth:login", "order:new", "order:cancel"}:
            raise ValueError("unsupported StandX Order Response method")
        self._pending_request_ids.add(request_id)
        self._pending_requests[request_id] = {"method": method, "params": dict(params)}
        return {
            "session_id": self.session_id,
            "request_id": request_id,
            "method": method,
            "header": {},
            "params": json.dumps(params, separators=(",", ":"), ensure_ascii=False),
        }

    def resolve(self, response: dict[str, Any]) -> dict[str, Any]:
        request_id = response.get("request_id")
        if isinstance(request_id, str):
            self._pending_request_ids.discard(request_id)
            self._pending_requests.pop(request_id, None)
        return response

    async def recover_pending(
        self,
        query: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        recovered: list[dict[str, Any]] = []
        for request_id, request in tuple(self._pending_requests.items()):
            cl_ord_id = request["params"].get("cl_ord_id")
            if not isinstance(cl_ord_id, str):
                continue
            result = await query(cl_ord_id)
            recovered.append(result)
            self._pending_request_ids.discard(request_id)
            self._pending_requests.pop(request_id, None)
        return recovered

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
