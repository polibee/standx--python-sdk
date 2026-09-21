# StandX Python SDK

Typed Python client for the StandX Perps API documented in `docs/standx.md`.

The SDK is under staged development. It defaults to `PAPER` and does not
perform real trading in its automated tests.

## Usage

```python
from decimal import Decimal

from standx_sdk import ClientConfig, StandXClient
from standx_sdk.models.order import CreateOrderRequest, OrderSide, OrderType, TimeInForce

client = StandXClient(ClientConfig(base_url="https://perps.standx.com"))

rules = await client.markets.symbol_info("BTC-USD")
balance = await client.account.balance()

order = CreateOrderRequest(
    symbol="BTC-USD",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    qty=Decimal("0.1"),
    price=Decimal("50000"),
    time_in_force=TimeInForce.GTC,
    reduce_only=False,
    cl_ord_id="client-example-1",
)
submission = await client.orders.create(order)
current = await client.orders.query_order(cl_ord_id="client-example-1")

balance = await client.account.balance_snapshot()
positions = await client.account.position_snapshots(symbol="BTC-USD")

market = client.streams.market()
await market.connect()
await market.authenticate("<jwt-from-login>")
await market.subscribe("price", "BTC-USD")
await market.subscribe("order")
price_event = await market.receive()
await market.close_async()
await client.close_async()
```

默认配置使用 StandX 文档中的 REST 和两个 WebSocket endpoint。离线测试可注入自定义 `HttpTransport`，也可以通过 `ClientConfig` 覆盖 endpoint；SDK 不会在测试中访问真实账户。

`new_order` and `cancel_order` responses indicate submission/acceptance, not
final matching. Use `client.streams.order_response()` with a shared
`session_id` to correlate asynchronous order responses.

登录成功后 token 会自动同步到客户端共享的 REST transport。异步应用退出时调用 `await client.close_async()` 释放 HTTP 和 WebSocket 资源。

For a request that was submitted but not confirmed, query the order again with
the client order ID. The typed REST methods return `Order`, `BalanceSnapshot`,
and `PositionSnapshot` DTOs with decimal values represented by `Decimal`.

## Development

```text
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
mypy src
python -m build
```
