import asyncio
from decimal import Decimal

import httpx

from standx_sdk.domain.markets import MarketsApi
from standx_sdk.transport.http import HttpTransport


def test_query_symbol_info_maps_documented_rules() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query_symbol_info"
        assert request.url.params["symbol"] == "BTC-USD"
        return httpx.Response(
            200,
            json=[
                {
                    "base_asset": "BTC",
                    "base_decimals": 9,
                    "created_at": "2025-07-10T05:15:32Z",
                    "def_leverage": "10",
                    "depth_ticks": "0.01,0.1,1",
                    "enabled": True,
                    "maker_fee": "0.0001",
                    "max_leverage": "20",
                    "max_open_orders": "100",
                    "max_order_qty": "100",
                    "max_position_size": "1000",
                    "min_order_qty": "0.0001",
                    "price_cap_ratio": "0.3",
                    "price_floor_ratio": "0.3",
                    "price_tick_decimals": 2,
                    "qty_tick_decimals": 4,
                    "quote_asset": "DUSD",
                    "quote_decimals": 9,
                    "symbol": "BTC-USD",
                    "taker_fee": "0.0004",
                    "updated_at": "2025-07-10T05:15:32Z",
                }
            ],
        )

    api = MarketsApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))
    rules = asyncio.run(api.symbol_info("BTC-USD"))

    assert rules.min_order_qty == Decimal("0.0001")
    assert rules.depth_ticks == (Decimal("0.01"), Decimal("0.1"), Decimal(1))
