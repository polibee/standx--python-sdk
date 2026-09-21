"""Public StandX SDK facade."""

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

    def market(self, *, transport: WebSocketTransport | None = None) -> MarketStream:
        stream = MarketStream(self._config.market_stream_url, transport=transport)
        self._created.append(stream)
        return stream

    def order_response(
        self,
        *,
        session_id: str = "sdk-session",
        transport: WebSocketTransport | None = None,
    ) -> OrderResponseStream:
        stream = OrderResponseStream(
            self._config.order_response_url,
            session_id=session_id,
            transport=transport,
        )
        self._created.append(stream)
        return stream

    async def close_async(self) -> None:
        for stream in self._created:
            await stream.close_async()


class StandXClient:
    def __init__(
        self,
        config: ClientConfig,
        signer: WalletSigner | None = None,
        *,
        request_signer: RequestSigner | None = None,
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
        )
        self.markets = MarketsApi(transport)
        self.account = AccountApi(transport)
        self.positions = PositionsApi(self.account)
        self.trades = TradesApi(self.account)
        self.orders = OrdersApi(transport)
        self.streams = _Streams(config)

    async def close_async(self) -> None:
        await self.streams.close_async()
        await self.http_transport.aclose()
        if self.auth_transport is not self.http_transport:
            close = getattr(self.auth_transport, "aclose", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
