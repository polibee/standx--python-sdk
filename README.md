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
        candles = await client.markets.kline_history(
            "BTC-USD", 1700000000, 1700003600, "5", countback=12
        )
        server_time = await client.markets.server_time()
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

如果官方同时提供 JWT 和匹配的 Ed25519 请求签名私钥，可以使用统一凭据配置，
Order Response Stream 会自动为下单/撤单请求生成签名 headers：

```python
from standx_sdk import ClientConfig, StandXClient, StandXCredentials

credentials = StandXCredentials(
    access_token=official_jwt,
    request_signing_key=StandXCredentials.decode_request_signing_key(
        official_ed25519_private_key
    ),
)
client = StandXClient(ClientConfig(base_url="https://perps.standx.com"), credentials=credentials)
order_stream = client.order_response_stream(session_id="trading-session")
await order_stream.connect()
await order_stream.authenticate(request_id="auth-request-1")
await order_stream.send_request(
    "order:new",
    {"symbol": "BTC-USD", "side": "buy", "qty": "0.1"},
    request_id="order-request-1",
)
```

`decode_request_signing_key` 支持官方 API Token 常用的 base58、hex、base64/base64url
编码，以及 Solana 示例中的 64-byte secret key（按官方约定取前 32-byte）。最终私钥
必须是匹配 JWT 的 32-byte Ed25519 key；SDK 不会把凭据写入日志或持久化，也不会对
未知长度静默截断。手工传入 `header` 仍然可以覆盖自动签名结果。

默认配置使用 StandX 文档中的 REST 和两个 WebSocket endpoint。离线测试可注入自定义 `HttpTransport`，也可以通过 `ClientConfig` 覆盖 endpoint；SDK 不会在测试中访问真实账户。

`ClientConfig.timeout_seconds`会应用到 REST HTTP client。网络超时和服务端限流会转换为带稳定错误码的 `StandXError`，调用方可以根据 `retryable` 和 `retry_after_seconds`决定是否重试。

REST transport 默认启用 StandX credit token-bucket 限流：每次请求 45 credits、900 credits burst、每秒补充 1,000 credits。创建订单和撤单不会因为 429 被 SDK 自动重试。

下单前可将 `await client.markets.symbol_info(symbol)` 返回的规则传给 `client.orders.create(order, rules=rules)`；SDK 会按 StandX 的最小/最大数量、精度、最大杠杆和 reduce-only 可用仓位进行本地拒绝校验。

`new_order` and `cancel_order` responses indicate submission/acceptance, not
final matching. Use `client.streams.order_response()` with a shared
`session_id` to correlate asynchronous order responses.

创建 Order Response Stream 后，SDK 会自动把同一个 `session_id` 设置到共享 REST
transport 的 `x-session-id` 请求头，保证随后 `new_order` / `cancel_order` 请求与
异步订单响应流关联。若切换到新的 response stream，会以新的 session ID 为准。

For `order:new` and `order:cancel`, the Order Response Stream header must contain
matching `x-request-id`, a non-empty `x-request-timestamp`, and a non-empty
`x-request-signature`. The example signature is a placeholder; applications must
generate it with the documented request-signing flow.

Order Response Stream 的 `accepted` 只表示网关接受请求；最终订单状态仍需读取用户订单流或通过 REST 查询恢复。断线重连不会自动重复发送创建订单或撤单请求。

登录成功后 token 会自动同步到客户端共享的 REST transport。异步应用退出时调用 `await client.close_async()` 释放 HTTP 和 WebSocket 资源。

如果应用已经从安全的凭据管理系统取得 JWT，可以跳过钱包登录，直接注入
`access_token`：

```python
client = StandXClient(
    ClientConfig(base_url="https://perps.standx.com"),
    access_token=load_jwt_from_secret_store(),
    request_signer=Ed25519RequestSigner(load_request_signing_key()),
)
```

这里的两个凭据用途不同：钱包签名器只负责获取 JWT；`access_token` 负责
Bearer 认证；`Ed25519RequestSigner` 负责文档要求的请求体签名。三者可以按
实际 endpoint 需求组合使用。SDK 不读取或持久化钱包私钥，token 失效后也不会
自动刷新；应用应重新登录或重新注入 token。可通过
`client.auth.set_access_token(None)` 清理共享 REST transport 的认证状态。

认证过期后可显式恢复：传入新的 JWT，或省略参数让已配置的 `WalletSigner`
重新执行登录。REST token 会先更新，已认证的 Market Stream 会使用原来的
用户 channel 和 impersonation 参数重新认证；Order Response Stream 中未确认
的订单请求不会自动重放，必须通过订单查询恢复。

也可以通过 `StandXClient(auth_recovery=...)` 注入异步恢复回调。回调会在本地
JWT 过期或 GET 请求收到 401 时执行一次；安全 GET 会重试一次，POST 请求不会
因 401 自动重放，避免重复下单、撤单或修改杠杆。

```python
await client.reauthenticate(new_token)
# 钱包模式：await client.reauthenticate()
```

市场 K 线使用文档定义的分辨率（例如 `1T`、`3S`、`1`、`5`、`15`、`60`、`1D`、`1W`、`1M`）；SDK 会校验并行数组长度和有限 Decimal 数值。`client.markets.health()`只接受服务端纯文本 `OK`，否则返回 `PROTOCOL_ERROR`。

也可以使用异步上下文管理器自动释放资源：

```python
async with StandXClient(ClientConfig(base_url="https://perps.standx.com")) as client:
    balance = await client.account.balance()
```

Client 关闭是幂等的；关闭后不能再创建新的 Market Stream 或 Order Response Stream。

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
