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

## Environment, dependencies, and package requirements

### Runtime environment

- Python **3.11 or newer**; Python 3.12–3.14 are also supported by the package configuration.
- Windows, Linux, and macOS are supported as long as Python can install the dependencies.
- No Node.js, Go, Docker, database, Redis, or blockchain node is required by the SDK.
- Internet access is required only when calling the real StandX REST/WebSocket endpoints.
- PAPER/LIVE selection is explicit through `ClientConfig.environment`; the default is `PAPER`.

### Runtime packages

The package installs these runtime dependencies automatically:

| Package | Version | Purpose |
|---|---:|---|
| `httpx` | `>=0.27` | Async REST transport |
| `websockets` | `>=15.0` | Market and order WebSocket streams |
| `PyNaCl` | `>=1.5` | Ed25519 request signing |

The installable package name is `standx-python-sdk`; the import name is `standx_sdk`.

### Development packages

Install the optional `dev` group for repository development:

| Package | Version | Purpose |
|---|---:|---|
| `pytest` | `>=8` | Offline test suite |
| `ruff` | `>=0.6` | Linting and formatting checks |
| `mypy` | `>=1.11` | Static type checking |
| `build` | `>=1.2` | Wheel/package build |

Development commands do not require live credentials and do not access real trading endpoints.

### Credentials required by feature

- Public market endpoints: no credential required.
- Authenticated queries: a StandX JWT (`access_token`).
- Signed orders, cancellations, leverage, and margin-mode changes: JWT plus a matching 32-byte
  Ed25519 request-signing key.
- Wallet login: an application-provided `WalletSigner`; the SDK does not implement wallet custody.

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

<a href="https://standx.com/referral?code=niubiii"><img alt="Join StandX with referral" src="https://img.shields.io/badge/Join%20StandX%20with%20referral-niubiii-2563eb?style=for-the-badge&labelColor=111827"></a>

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

## Error diagnosis

`StandXError.code` is stable and safe to branch on: `401` becomes `AUTH_FAILED`, `403` becomes
`PERMISSION_DENIED`, `404` becomes `NOT_FOUND` (check environment, API version, domain, or
credential type), and `5xx` becomes `SERVER_ERROR`. `retryable` indicates whether a retry can be
considered. For network failures, `transport_error_type` identifies the sanitized cause, such as
`DNS error`, `TLS error`, `ProxyError`, `ConnectTimeout`, `ReadTimeout`, or `RemoteDisconnect`.
The SDK never includes JWTs, private keys, authorization headers, URLs, or raw exception text in
these diagnostic messages.

```python
try:
    await client.markets.overview()
except StandXError as exc:
    print(exc.code, exc.retryable, exc.transport_error_type)
```

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
