# StandX Python SDK

Typed Python client for the StandX Perps API documented in `docs/standx.md`.

The SDK defaults to `PAPER` and does not perform real trading in its automated tests.
See [CHANGELOG.md](CHANGELOG.md) for the current release scope and safety notes.

## Usage

```python
import asyncio
from decimal import Decimal

from standx_sdk import ClientConfig, StandXClient
from standx_sdk.auth.wallet import WalletSigner
from standx_sdk.domain import OrderStateReconciler
from standx_sdk.models.order import CreateOrderRequest, OrderSide, OrderType, TimeInForce
from standx_sdk.signing.request import Ed25519RequestSigner

class ApplicationWallet(WalletSigner):
    async def sign_login_message(self, message: str) -> str:
        # Delegate to the application's EVM/Solana wallet implementation.
        raise NotImplementedError


async def main() -> None:
    # Load the 32-byte request-signing key from a secure runtime secret store.
    request_signer = Ed25519RequestSigner(load_secret_bytes())
    client = StandXClient(
        ClientConfig(base_url="https://perps.standx.com"),
        signer=ApplicationWallet(chain="ethereum", address="0x..."),
        request_signer=request_signer,
    )

    try:
        login = await client.auth.login()

        rules = await client.markets.symbol_info("BTC-USD")
        balance = await client.account.balance()
        positions = await client.positions.list(symbol="BTC-USD")
        trades = await client.trades.list(symbol="BTC-USD", limit=50)

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
        submission = await client.orders.create(order, rules=rules)
        current = await client.orders.query_order(cl_ord_id=submission.cl_ord_id)

        # REST order creation is asynchronous. Correlate the response stream by session ID.
        order_stream = client.order_response_stream(session_id="application-session")
        await order_stream.connect()
        await order_stream.send_request(
            "order:cancel",
            {"cl_ord_id": submission.cl_ord_id},
            request_id="cancel-request-1",
            header={
                "x-request-id": "cancel-request-1",
                "x-request-timestamp": "1700000000000",
                "x-request-signature": "<base64-signature>",
            },
        )
        response = await order_stream.receive()
        cancellation = order_stream.decode_response(response)

        # User order events are notifications; re-read REST for a complete snapshot.
        reconciler = OrderStateReconciler(
            lambda cl_ord_id: client.orders.query_order(cl_ord_id=cl_ord_id)
        )
        market = client.market_stream()
        await market.connect()
        await market.authenticate(login.token, streams=["order"])
        event = await market.receive()
        order_snapshot = await reconciler.apply_user_event(market.decode(event))
        open_orders = await reconciler.restore_open_orders(client.orders.query_open_orders)
    finally:
        await client.close_async()


asyncio.run(main())
```

默认配置使用 StandX 文档中的 REST 和两个 WebSocket endpoint。离线测试可注入自定义 `HttpTransport`，也可以通过 `ClientConfig` 覆盖 endpoint；SDK 不会在测试中访问真实账户。

`ClientConfig.timeout_seconds`会应用到 REST HTTP client。网络超时和服务端限流会转换为带稳定错误码的 `StandXError`，调用方可以根据 `retryable` 和 `retry_after_seconds`决定是否重试。

REST transport 默认启用 StandX credit token-bucket 限流：每次请求 45 credits、900 credits burst、每秒补充 1,000 credits。创建订单和撤单不会因为 429 被 SDK 自动重试。

下单前可将 `await client.markets.symbol_info(symbol)` 返回的规则传给 `client.orders.create(order, rules=rules)`；SDK 会按 StandX 的最小/最大数量、精度、最大杠杆和 reduce-only 可用仓位进行本地拒绝校验。

`new_order` and `cancel_order` responses indicate submission/acceptance, not
final matching. Use `client.streams.order_response()` with a shared
`session_id` to correlate asynchronous order responses.

For `order:new` and `order:cancel`, the Order Response Stream header must contain
matching `x-request-id`, a non-empty `x-request-timestamp`, and a non-empty
`x-request-signature`. The example signature is a placeholder; applications must
generate it with the documented request-signing flow.

Order Response Stream 的 `accepted` 只表示网关接受请求；最终订单状态仍需读取用户订单流或通过 REST 查询恢复。断线重连不会自动重复发送创建订单或撤单请求。

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

The test suite is fully offline. A real `LIVE` configuration requires an explicit
`Environment.LIVE` choice and separately supplied credentials/signers.

The SDK does not store wallet keys, does not provide a concrete wallet adapter,
and does not claim that PAPER tests prove LIVE trading readiness. Keep all keys,
JWTs, and signatures in the application's secret-management boundary.
