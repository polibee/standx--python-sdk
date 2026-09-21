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
        token: str | None = None,
        impersonate: str | None = None,
        session_id: str | None = None,
        request_signer: RequestSigner | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, transport=transport)
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
        response = await self._client.get(path, params=params, headers=self._headers)
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
        response = await self._client.post(path, json=json, params=params, headers=headers)
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        retryable = response.status_code == 429 or response.status_code >= 500
        code = ErrorCode.RATE_LIMITED if response.status_code == 429 else ErrorCode.PROTOCOL_ERROR
        error = StandXError(code=code, message=f"HTTP {response.status_code}", retryable=retryable)
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            error.retry_after_seconds = float(retry_after)
        raise error

    async def aclose(self) -> None:
        await self._client.aclose()


def json_module_dumps(value: Mapping[str, object]) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
