"""StandX asynchronous order response stream envelopes."""

import asyncio
import inspect
import json
import math
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.exceptions import WebSocketException

from ..errors import ErrorCode, StandXError
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

    def request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        request_id: str,
        header: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not request_id:
            raise ValueError("request_id must not be empty")
        if method not in {"auth:login", "order:new", "order:cancel"}:
            raise ValueError("unsupported StandX Order Response method")
        request_header = dict(header or {})
        if method in {"order:new", "order:cancel"}:
            required_headers = {
                "x-request-id",
                "x-request-timestamp",
                "x-request-signature",
            }
            if not required_headers.issubset(request_header):
                raise ValueError("order requests require authentication header")
            if request_header["x-request-id"] != request_id:
                raise ValueError("x-request-id must match request_id")
            if not request_header["x-request-timestamp"] or not request_header["x-request-signature"]:
                raise ValueError("authentication headers must be non-empty")
        if request_id in self._pending_request_ids:
            raise ValueError("request_id is already pending")
        self._pending_request_ids.add(request_id)
        self._pending_requests[request_id] = {"method": method, "params": dict(params)}
        return {
            "session_id": self.session_id,
            "request_id": request_id,
            "method": method,
            "header": request_header,
            "params": json.dumps(params, separators=(",", ":"), ensure_ascii=False),
        }

    def resolve(self, response: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(response, dict):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response envelope must be an object",
            )
        request_id = response.get("request_id")
        if not isinstance(request_id, str):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response is missing request_id",
            )
        response_session_id = response.get("session_id")
        if response_session_id is not None and response_session_id != self.session_id:
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response session_id does not match stream session",
                request_id=request_id,
            )
        raw_code = response.get("code")
        if isinstance(raw_code, bool) or not isinstance(raw_code, int):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response code must be an integer",
                request_id=request_id,
            )
        self._pending_request_ids.discard(request_id)
        self._pending_requests.pop(request_id, None)
        return response

    def decode_response(self, response: dict[str, Any]) -> OrderResponseEvent:
        if not isinstance(response, dict):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response envelope must be an object",
            )
        request_id = response.get("request_id")
        if not isinstance(request_id, str):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response is missing request_id",
            )
        response_session_id = response.get("session_id")
        if response_session_id is not None and response_session_id != self.session_id:
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response session_id does not match stream session",
                request_id=request_id,
            )
        raw_code = response.get("code")
        if isinstance(raw_code, bool) or not isinstance(raw_code, int):
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "Order Response code must be an integer",
                request_id=request_id,
            )
        code = raw_code
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
        max_delay: float | None = None,
        jitter: Callable[[float], float] | None = None,
        sleep: Callable[[float], object] | None = None,
    ) -> None:
        if self.closed:
            raise RuntimeError("closed stream cannot connect")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not math.isfinite(initial_delay) or initial_delay < 0:
            raise ValueError("initial_delay must be finite and non-negative")
        if max_delay is not None and (not math.isfinite(max_delay) or max_delay <= 0):
            raise ValueError("max_delay must be finite, positive, or None")
        pause = sleep or asyncio.sleep
        delay = initial_delay
        for attempt in range(max_attempts):
            try:
                await self.connect()
                return
            except (ConnectionError, OSError, TimeoutError, WebSocketException):
                if attempt == max_attempts - 1:
                    raise
                wait = delay if max_delay is None else min(delay, max_delay)
                if jitter is not None:
                    wait = jitter(wait)
                if max_delay is not None:
                    wait = min(wait, max_delay)
                if not math.isfinite(wait) or wait < 0:
                    raise ValueError("jitter must return a finite, non-negative delay")
                result = pause(wait)
                if inspect.isawaitable(result):
                    await result
                delay *= 2

    async def reconnect(self) -> None:
        if self.closed:
            raise RuntimeError("closed stream cannot reconnect")
        await self.transport.close()
        await self.connect()

    async def send_request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        request_id: str,
        header: dict[str, str] | None = None,
    ) -> None:
        try:
            await self.transport.send(
                json.dumps(
                    self.request(method, params, request_id=request_id, header=header),
                    separators=(",", ":"),
                )
            )
        except (ConnectionError, OSError, TimeoutError, WebSocketException) as exc:
            raise StandXError(
                ErrorCode.WS_DISCONNECTED,
                "Order Response Stream connection disconnected while sending",
                retryable=True,
            ) from exc

    async def authenticate(
        self,
        token: str,
        *,
        request_id: str,
        impersonate: str | None = None,
    ) -> OrderResponseEvent:
        """Authenticate the stream using the documented auth:login request."""

        if not token.strip():
            raise ValueError("token must not be empty")
        params: dict[str, Any] = {"token": token}
        if impersonate is not None:
            params["impersonate"] = impersonate
        await self.send_request("auth:login", params, request_id=request_id)
        return self.decode_response(await self.receive())

    async def receive(self) -> Any:
        try:
            return json.loads(await self.transport.receive())
        except (ConnectionError, OSError, TimeoutError, WebSocketException) as exc:
            raise StandXError(
                ErrorCode.WS_DISCONNECTED,
                "Order Response Stream connection disconnected",
                retryable=True,
            ) from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise StandXError(
                ErrorCode.PROTOCOL_ERROR,
                "invalid JSON from Order Response Stream",
            ) from exc

    async def close_async(self) -> None:
        self.close()
        await self.transport.close()
