"""StandX asynchronous order response stream envelopes."""

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from ..models.order import Order
from ..models.stream import OrderResponseEvent
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

    def decode_response(self, response: dict[str, Any]) -> OrderResponseEvent:
        request_id = response.get("request_id")
        if not isinstance(request_id, str):
            raise TypeError("Order Response is missing request_id")
        code = int(response.get("code", 0))
        status = response.get("status")
        if status == "accepted":
            state = "accepted"
        elif code >= 400:
            state = "rejected"
        elif code == 0:
            state = "success"
        else:
            state = "unknown"
        self.resolve(response)
        return OrderResponseEvent(
            request_id=request_id,
            code=code,
            state=state,
            message=response.get("message") if isinstance(response.get("message"), str) else None,
        )

    async def recover_pending(
        self,
        query: Callable[[str], Awaitable[dict[str, Any] | Order | None]],
    ) -> list[dict[str, Any] | Order]:
        recovered: list[dict[str, Any] | Order] = []
        for request_id, request in tuple(self._pending_requests.items()):
            cl_ord_id = request["params"].get("cl_ord_id")
            if not isinstance(cl_ord_id, str):
                continue
            result = await query(cl_ord_id)
            if result is None:
                continue
            recovered.append(result)
            self._pending_request_ids.discard(request_id)
            self._pending_requests.pop(request_id, None)
        return recovered

    async def connect(self) -> None:
        if self.closed:
            raise RuntimeError("closed stream cannot connect")
        await self.transport.connect()

    async def connect_with_backoff(
        self,
        *,
        max_attempts: int = 5,
        initial_delay: float = 0.5,
        sleep: Callable[[float], object] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if initial_delay < 0:
            raise ValueError("initial_delay must not be negative")
        pause = sleep or asyncio.sleep
        delay = initial_delay
        for attempt in range(max_attempts):
            try:
                await self.connect()
                return
            except Exception:
                if attempt == max_attempts - 1:
                    raise
                result = pause(delay)
                if inspect.isawaitable(result):
                    await result
                delay *= 2

    async def reconnect(self) -> None:
        if self.closed:
            raise RuntimeError("closed stream cannot reconnect")
        await self.transport.close()
        await self.connect()

    async def send_request(self, method: str, params: dict[str, Any], *, request_id: str) -> None:
        await self.transport.send(
            json.dumps(self.request(method, params, request_id=request_id), separators=(",", ":"))
        )

    async def receive(self) -> Any:
        return json.loads(await self.transport.receive())

    async def close_async(self) -> None:
        self.close()
        await self.transport.close()
