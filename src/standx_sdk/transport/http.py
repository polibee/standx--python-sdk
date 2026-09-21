"""Async HTTP transport for documented StandX REST endpoints."""

import json
import time
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from ..errors import ErrorCode, StandXError


class RequestSigner(Protocol):
    def sign_request(
        self, version: str, request_id: str, timestamp: int, payload: str
    ) -> dict[str, str]: ...


class HttpTransport:
    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        timeout_seconds: float = 10.0,
        token: str | None = None,
        impersonate: str | None = None,
        session_id: str | None = None,
        request_signer: RequestSigner | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self.base_url, transport=transport, timeout=timeout_seconds
        )
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        if impersonate:
            self._headers["x-impersonate"] = impersonate
        if session_id:
            self._headers["x-session-id"] = session_id
        self._request_signer = request_signer

    @property
    def token(self) -> str | None:
        value = self._headers.get("Authorization")
        return value.removeprefix("Bearer ") if value else None

    def set_token(self, token: str | None) -> None:
        if token is None:
            self._headers.pop("Authorization", None)
        else:
            self._headers["Authorization"] = f"Bearer {token}"

    async def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        try:
            response = await self._client.get(path, params=params, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise StandXError(
                ErrorCode.REQUEST_TIMEOUT, "HTTP request timed out", retryable=True
            ) from exc
        self._raise_for_status(response)
        return response.json()

    async def post(
        self,
        path: str,
        *,
        json: Mapping[str, object],
        signed: bool = False,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        headers = dict(self._headers)
        if signed:
            if self._request_signer is None:
                raise ValueError("signed request requires request_signer")
            payload = json_module_dumps(json)
            request_id = str(uuid.uuid4())
            timestamp = int(time.time() * 1000)
            headers.update(self._request_signer.sign_request("v1", request_id, timestamp, payload))
        try:
            response = await self._client.post(path, json=json, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise StandXError(
                ErrorCode.REQUEST_TIMEOUT, "HTTP request timed out", retryable=True
            ) from exc
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code_by_status = {
            400: ErrorCode.VALIDATION_ERROR,
            401: ErrorCode.AUTH_FAILED,
            403: ErrorCode.AUTH_FAILED,
            408: ErrorCode.REQUEST_TIMEOUT,
            429: ErrorCode.RATE_LIMITED,
        }
        code = code_by_status.get(response.status_code, ErrorCode.PROTOCOL_ERROR)
        retryable = response.status_code in {408, 429} or response.status_code >= 500
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = payload.get("message") if isinstance(payload, dict) else None
        request_id = response.headers.get("x-request-id")
        if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
            request_id = payload["request_id"]
        error = StandXError(
            code=code,
            message=str(message) if message else f"HTTP {response.status_code}",
            request_id=request_id,
            retryable=retryable,
        )
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            error.retry_after_seconds = float(retry_after)
        raise error

    async def aclose(self) -> None:
        await self._client.aclose()


def json_module_dumps(value: Mapping[str, object]) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
