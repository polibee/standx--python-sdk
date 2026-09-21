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
)
submission = await client.orders.create(order)

market = client.streams.market()
await market.connect()
await market.subscribe("price", "BTC-USD")
price_event = await market.receive()
await market.close_async()
```

`new_order` and `cancel_order` responses indicate submission/acceptance, not
final matching. Use `client.streams.order_response()` with a shared
`session_id` to correlate asynchronous order responses.

## Development

```text
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
mypy src
python -m build
```
