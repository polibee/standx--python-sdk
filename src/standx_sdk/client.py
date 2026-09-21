"""Public StandX SDK facade."""

from .auth.service import AuthService
from .auth.wallet import WalletSigner
from .config import ClientConfig
from .domain.account import AccountApi
from .domain.markets import MarketsApi
from .domain.orders import OrdersApi
from .streams.market import MarketStream
from .streams.order_response import OrderResponseStream
from .transport.http import HttpTransport


class _Streams:
    def __init__(self, config: ClientConfig) -> None:
        self._config = config

    def market(self) -> MarketStream:
        return MarketStream("wss://perps.standx.com/ws-stream/v1")

    def order_response(self, *, session_id: str = "sdk-session") -> OrderResponseStream:
        return OrderResponseStream("wss://perps.standx.com/ws-api/v1", session_id=session_id)


class StandXClient:
    def __init__(self, config: ClientConfig, signer: WalletSigner | None = None) -> None:
        self.config = config
        transport = HttpTransport(config.base_url)
        self.auth = AuthService(HttpTransport("https://api.standx.com"), signer)
        self.markets = MarketsApi(transport)
        self.account = AccountApi(transport)
        self.orders = OrdersApi(transport)
        self.streams = _Streams(config)
