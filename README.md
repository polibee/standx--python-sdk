# StandX Python SDK

Typed, asynchronous Python SDK for the documented StandX Perps REST and WebSocket APIs.

Language: **English** · [简体中文](README.zh-CN.md)

> The SDK defaults to `PAPER`. Automated tests are offline and never place real orders.
> Treat `LIVE` as a production integration that requires your own risk controls and secret management.

## Features

- Typed REST APIs for markets, prices, depth, trades, candles, accounts, positions, funding, orders, leverage, and margin mode.
- Market Stream for `price`, `depth_book`, `public_trade`, plus authenticated user channels.
- Order Response Stream for asynchronous order acceptance, execution, and cancellation responses.
- Ed25519 request signing with base58, hex, base64, and base64url credential decoding.
- Decimal-safe quantity and price validation using symbol rules.
- Automatic `x-session-id` binding between REST orders and the Order Response Stream.
- Reconnect backoff, subscription recovery, JWT expiry recovery, rate limiting, and order-state reconciliation.
- No wallet transfer, deposit, withdrawal, or bridge operations.

## Requirements

- Python 3.11+
- A StandX JWT for authenticated queries
- A matching Ed25519 request-signing key for signed mutations such as orders and leverage changes

## Install

### Install from GitHub

```bash
python -m pip install "git+https://github.com/polibee/standx--python-sdk.git"
```

### Clone for development

```bash
git clone https://github.com/polibee/standx--python-sdk.git
cd standx--python-sdk
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
# source .venv/bin/activate

python -m pip install -e ".[dev]"
```

## Credentials

StandX uses two separate credentials:

1. `access_token`: JWT used for Bearer authentication and authenticated queries.
2. `request_signing_key`: matching Ed25519 private key required by signed POST requests.

API Token request-signing keys are self-custodial. Store them in a secret manager or environment
variables; do not commit them. The SDK accepts the encoded key directly:

```python
from standx_sdk import StandXCredentials

credentials = StandXCredentials(
    access_token="<JWT>",
    request_signing_key=StandXCredentials.decode_request_signing_key(
        "<base58-or-hex-or-base64-key>"
    ),
)
```

The decoder supports base58, hex, base64/base64url, and the 64-byte Solana secret-key format
(using its first 32 bytes). Unknown lengths are rejected instead of being truncated.

JWT-only clients can query authenticated read endpoints, but cannot create signed orders:

```python
from standx_sdk import ClientConfig, StandXClient

client = StandXClient(
    ClientConfig(base_url="https://perps.standx.com"),
    access_token="<JWT>",
)
```

## Referral registration

If you have never connected a wallet to StandX, open the referral link before the first wallet
connection:

```yaml
first_time_standx_registration: "https://standx.com/referral?code=niubiii"
```

Referral codes belong to the official web onboarding flow. They are not REST order parameters,
and this SDK does not try to attach them to authentication or trading requests. Existing wallet
accounts should follow the current rules shown by StandX; the SDK does not assume that a referral
code can be added retroactively.

## Query a market

```python
import asyncio
from standx_sdk import ClientConfig, StandXClient


async def main() -> None:
    async with StandXClient(
        ClientConfig(base_url="https://perps.standx.com")
    ) as client:
        price = await client.markets.symbol_price("BTC-USD")
        market = await client.markets.symbol_market("BTC-USD")
        depth = await client.markets.depth_book("BTC-USD")
        trades = await client.markets.recent_trades("BTC-USD", limit=20)
        rules = await client.markets.symbol_info("BTC-USD")
        candles = await client.markets.kline_history(
            "BTC-USD", 1700000000, 1700003600, "5", countback=100
        )
        print(price.last_price, market.mark_price)
        print(depth.bids, depth.asks)
        print(rules.min_order_qty, rules.qty_tick_decimals)
        print(len(trades), len(candles.bars))


asyncio.run(main())
```

Available market REST methods include `overview()`, `symbol_price()`, `symbol_market()`,
`depth_book()`, `recent_trades()`, `symbol_info()`, `kline_history()`, `server_time()`, and
`health()`.

## Real-time market data

```python
async with StandXClient(
    ClientConfig(base_url="https://perps.standx.com")
) as client:
    stream = client.market_stream()
    await stream.connect()
    await stream.subscribe("price", symbol="BTC-USD")
    await stream.subscribe("depth_book", symbol="BTC-USD")

    while True:
        event = stream.decode(await stream.receive())
        print(event)
```

Authenticated channels are `order`, `position`, `balance`, and `trade`; call
`await stream.authenticate(token, streams=[...])` before subscribing to them.

## Signed order flow

```python
from decimal import Decimal
from standx_sdk import ClientConfig, StandXClient, StandXCredentials
from standx_sdk.models.order import CreateOrderRequest, OrderSide, OrderType, TimeInForce


async def trade() -> None:
    credentials = StandXCredentials(
        access_token="<JWT>",
        request_signing_key=StandXCredentials.decode_request_signing_key("<KEY>"),
    )
    async with StandXClient(
        ClientConfig(base_url="https://perps.standx.com"),
        credentials=credentials,
    ) as client:
        rules = await client.markets.symbol_info("BTC-USD")
        request = CreateOrderRequest(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            qty=Decimal("0.1"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            cl_ord_id="example-order-001",
        )
        submission = await client.orders.create(request, rules=rules)
        print(submission.request_id, submission.cl_ord_id)

        order_stream = client.order_response_stream(session_id="example-session")
        await order_stream.connect()
        await order_stream.authenticate()
        response = await order_stream.send_request(
            "order:cancel",
            {"cl_ord_id": submission.cl_ord_id},
            request_id="cancel-example-001",
        )
        print(order_stream.decode_response(response))
```

Creating an Order Response Stream automatically applies its `session_id` to the shared REST
transport as `x-session-id`. The `accepted` response means the gateway accepted the request;
use the user order stream or REST queries for final state. Requests are never replayed after a
timeout or reconnect.

## PAPER and LIVE

```python
from standx_sdk import ClientConfig, Environment

paper = ClientConfig(
    base_url="https://perps.standx.com",
    environment=Environment.PAPER,
)

# LIVE must be an explicit application decision.
live = ClientConfig(
    base_url="https://perps.standx.com",
    environment=Environment.LIVE,
)
```

The SDK does not infer LIVE credentials, store keys, or implement wallet funding. Use a
least-privilege API Token with `Trade` enabled and `Withdraw` disabled for trading bots.

## Development and verification

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
```

The repository also contains `tools/verify_credentials.py` for a read-only PAPER check using
an ignored local `.env`. It never submits orders or wallet operations.

## Documentation

- [中文文档](README.zh-CN.md)
- [SDK design](docs/standx-sdk-design.md)
- [Portable SDK design for other languages](docs/standx-sdk-portable-design.md)
- [StandX protocol notes](docs/standx.md)
- [Changelog](CHANGELOG.md)
- [Official StandX authentication](https://docs.standx.com/standx-api/perps-auth)
- [Official API Token guide](https://docs.standx.com/docs/standx-perps-solutions/api-token)

## Infrastructure recommendations

The following are optional infrastructure referral links and are not required by the SDK:

- [Deploy on Vast.ai](https://cloud.vast.ai/?ref_id=91181)
- [![DigitalOcean Referral Badge](https://web-platforms.sfo2.cdn.digitaloceanspaces.com/WWW/Badge%201.svg)](https://www.digitalocean.com/?refcode=497113351f20&utm_campaign=Referral_Invite&utm_medium=Referral_Program&utm_source=badge)

## License and safety

Keep JWTs, signing keys, and signatures inside your application's secret-management boundary.
PAPER tests do not prove LIVE trading readiness. Review StandX risk, rate-limit, and permission
requirements before deploying automated trading.
