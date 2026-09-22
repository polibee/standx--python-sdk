"""Public StandX SDK facade."""

from collections.abc import Awaitable, Callable
from typing import Self

from .auth.service import AuthService, AuthTransport
from .auth.wallet import WalletSigner
from .config import ClientConfig
from .domain.account import AccountApi
from .domain.account_views import PositionsApi, TradesApi
from .domain.markets import MarketsApi
from .domain.orders import OrdersApi
from .streams.market import MarketStream
from .streams.order_response import OrderResponseStream
from .transport.http import HttpTransport, RequestSigner
from .transport.websocket import WebSocketTransport


class _Streams:
    def __init__(self, config: ClientConfig) -> None:
        self._config = config
        self._created: list[MarketStream | OrderResponseStream] = []
        self._closed = False

    def market(self, *, transport: WebSocketTransport | None = None) -> MarketStream:
        if self._closed:
            raise RuntimeError("closed client cannot create streams")
        stream = MarketStream(self._config.market_stream_url, transport=transport)
        self._created.append(stream)
        return stream

    def order_response(
        self,
        *,
        session_id: str = "sdk-session",
        transport: WebSocketTransport | None = None,
    ) -> OrderResponseStream:
        if self._closed:
            raise RuntimeError("closed client cannot create streams")
        stream = OrderResponseStream(
            self._config.order_response_url,
            session_id=session_id,
            transport=transport,
        )
        self._created.append(stream)
        return stream

    async def close_async(self) -> None:
        if self._closed:
            return
        for stream in self._created:
            await stream.close_async()
        self._closed = True

    async def reauthenticate(self, token: str) -> None:
        for stream in self._created:
            if isinstance(stream, MarketStream):
                await stream.reauthenticate(token)

class StandXClient:
    def __init__(
        self,
        config: ClientConfig,
        signer: WalletSigner | None = None,
        *,
        access_token: str | None = None,
        request_signer: RequestSigner | None = None,
        auth_recovery: Callable[[], Awaitable[str]] | None = None,
        http_transport: HttpTransport | None = None,
        auth_transport: AuthTransport | None = None,
    ) -> None:
        self.config = config
        transport = http_transport or HttpTransport(
            config.base_url,
            timeout_seconds=config.timeout_seconds,
            request_signer=request_signer,
        )
        self.http_transport = transport
        self.auth_transport = auth_transport or HttpTransport(
            config.auth_base_url, timeout_seconds=config.timeout_seconds
        )
        self.auth = AuthService(
            self.auth_transport,
            signer,
            on_token=transport.set_token,
            on_token_expiry=transport.set_token_expiry,
        )
        if access_token is not None:
            self.auth.set_access_token(access_token)
        if auth_recovery is not None:
            transport.set_auth_recovery(auth_recovery)
        elif signer is not None:
            transport.set_auth_recovery(self.reauthenticate)
        self.markets = MarketsApi(transport)
        self.account = AccountApi(transport)
        self.positions = PositionsApi(self.account)
        self.trades = TradesApi(self.account)
        self.orders = OrdersApi(transport, rules_provider=self.markets.symbol_info)
        self.streams = _Streams(config)
        self._closed = False

    async def __aenter__(self) -> Self:
        if self._closed:
            raise RuntimeError("closed client cannot be entered")
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        await self.close_async()

    def market_stream(self, *, transport: WebSocketTransport | None = None) -> MarketStream:
        """Create and register a Market Stream using the configured endpoint."""

        return self.streams.market(transport=transport)

    def order_response_stream(
        self,
        *,
        session_id: str = "sdk-session",
        transport: WebSocketTransport | None = None,
    ) -> OrderResponseStream:
        """Create and register an Order Response Stream."""

        return self.streams.order_response(session_id=session_id, transport=transport)

    async def close_async(self) -> None:
        if self._closed:
            return
        await self.streams.close_async()
        await self.http_transport.aclose()
        if self.auth_transport is not self.http_transport:
            close = getattr(self.auth_transport, "aclose", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        self._closed = True

    async def reauthenticate(self, access_token: str | None = None) -> str:
        """Refresh REST and authenticated Market Streams with a new JWT.

        When ``access_token`` is omitted, the configured wallet signer is used to
        run the documented login flow. Order Response requests are never replayed.
        """

        if access_token is None:
            result = await self.auth.login()
            token = result.token
        else:
            self.auth.set_access_token(access_token)
            token = access_token
        await self.streams.reauthenticate(token)
        return token
