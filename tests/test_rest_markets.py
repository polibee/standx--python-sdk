import asyncio
from decimal import Decimal

import httpx

from standx_sdk.domain.markets import MarketsApi
from standx_sdk.models.market import DepthBook, MarketOverview, SymbolMarket, SymbolPrice
from standx_sdk.models.trade import RecentTrade
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
    assert rules.enabled is True
    assert rules.created_at == "2025-07-10T05:15:32Z"
    assert rules.updated_at == "2025-07-10T05:15:32Z"


def test_market_api_maps_documented_market_and_depth_dtos() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/query_market_overview":
            return httpx.Response(
                200,
                json={
                    "summary": {
                        "open_interest_notional": "100",
                        "symbol_count": 1,
                        "volume_quote_24h": "200",
                    },
                    "symbols": [
                        {
                            "base": "BTC",
                            "quote": "DUSD",
                            "symbol": "BTC-USD",
                            "last_price": "50000",
                            "mark_price": "50001",
                            "funding_rate": "0.0001",
                            "open_interest": "1",
                            "open_interest_notional": "50000",
                            "price_change_pct": 1.2,
                            "volume_24h": "2",
                            "volume_quote_24h": "100000",
                            "time": "2026-01-01T00:00:00Z",
                        }
                    ],
                },
            )
        if request.url.path == "/api/query_symbol_market":
            return httpx.Response(
                200,
                json={
                    "base": "BTC",
                    "quote": "DUSD",
                    "symbol": "BTC-USD",
                    "last_price": "50000",
                    "funding_rate": "0.1",
                    "spread": ["49999", "50001"],
                },
            )
        if request.url.path == "/api/query_symbol_price":
            return httpx.Response(
                200,
                json={
                    "base": "BTC",
                    "quote": "DUSD",
                    "symbol": "BTC-USD",
                    "last_price": "50000",
                    "spread_bid": "49999",
                },
            )
        return httpx.Response(
            200,
            json={"symbol": "BTC-USD", "asks": [["50001", "1"]], "bids": [["49999", "2"]]},
        )

    api = MarketsApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))

    async def collect() -> tuple[MarketOverview, SymbolMarket, SymbolPrice, DepthBook]:
        return await asyncio.gather(
            api.overview(),
            api.symbol_market("BTC-USD"),
            api.symbol_price("BTC-USD"),
            api.depth_book("BTC-USD"),
        )

    overview, market, price, book = asyncio.run(collect())
    assert overview.symbols[0].last_price == Decimal(50000)
    assert market.base == "BTC"
    assert market.quote == "DUSD"
    assert market.funding_rate == Decimal("0.1")
    assert market.spread == (Decimal(49999), Decimal(50001))
    assert price.base == "BTC"
    assert price.quote == "DUSD"
    assert price.spread_bid == Decimal(49999)
    assert book.asks == ((Decimal(50001), Decimal(1)),)


def test_recent_trade_snapshots_maps_documented_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query_recent_trades"
        assert request.url.params["symbol"] == "BTC-USD"
        assert request.url.params["limit"] == "2"
        return httpx.Response(
            200,
            json=[
                {
                    "is_buyer_taker": True,
                    "price": "121720.18",
                    "qty": "0.01",
                    "quote_qty": "1217.2018",
                    "symbol": "BTC-USD",
                    "time": "2025-08-11T03:48:47.086505Z",
                }
            ],
        )

    api = MarketsApi(HttpTransport("https://perps.standx.com", httpx.MockTransport(handler)))
    trades = asyncio.run(api.recent_trade_snapshots("BTC-USD", limit=2))

    assert trades == [
        RecentTrade(
            symbol="BTC-USD",
            price=Decimal("121720.18"),
            qty=Decimal("0.01"),
            quote_qty=Decimal("1217.2018"),
            is_buyer_taker=True,
            time="2025-08-11T03:48:47.086505Z",
        )
    ]
