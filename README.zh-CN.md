# StandX Python SDK

面向 StandX Perps REST 和 WebSocket API 的类型安全异步 Python SDK。

语言：**简体中文** · [English](README.md)

[![PyPI 下载量](https://img.shields.io/pypi/dm/standx-python-sdk?label=PyPI%20downloads)](https://pypi.org/project/standx-python-sdk/)

软件包发布到 PyPI 后，徽章会自动显示下载统计；从 GitHub 源码直接安装的数量不包含在该统计中。

> SDK 默认使用 `PAPER`。自动化测试完全离线，不会真实下单。
> `LIVE` 只能在应用完成风险控制、密钥管理和灰度验证后使用。

## 功能

- 行情、价格、深度、成交、K 线、账户、持仓、资金费率、订单、杠杆和保证金模式 REST API。
- Market Stream：`price`、`depth_book`、`public_trade` 以及用户数据频道。
- Order Response Stream：异步下单、成交和撤单结果。
- Ed25519 请求签名，支持 base58、hex、base64、base64url 凭证编码。
- 使用交易对规则进行 Decimal 精度、最小数量和 reduce-only 本地校验。
- REST 订单与 Order Response Stream 自动关联 `x-session-id`。
- 自动重连退避、订阅恢复、JWT 过期恢复、限流和订单状态恢复。
- 不实现钱包转账、充值、提现和 Bridge 操作。

## 环境、依赖和包要求

### 运行环境

- Python **3.11 或更高版本**；项目配置同时支持 Python 3.12–3.14。
- 支持 Windows、Linux 和 macOS，只要 Python 能够正常安装依赖即可。
- SDK 不要求 Node.js、Go、Docker、数据库、Redis 或区块链节点。
- 只有访问真实 StandX REST/WebSocket 服务时才需要网络连接。
- 通过 `ClientConfig.environment` 显式选择 PAPER/LIVE，默认是 `PAPER`。

### 运行时依赖包

安装 SDK 时会自动安装以下依赖：

| 包 | 版本 | 用途 |
|---|---:|---|
| `httpx` | `>=0.27` | 异步 REST 网络传输 |
| `websockets` | `>=15.0` | 行情和订单 WebSocket 流 |
| `PyNaCl` | `>=1.5` | Ed25519 请求签名 |

可安装包名称是 `standx-python-sdk`，代码导入名称是 `standx_sdk`。

### 开发依赖包

在源码仓库开发时安装 `dev` 可选依赖：

| 包 | 版本 | 用途 |
|---|---:|---|
| `pytest` | `>=8` | 离线测试 |
| `ruff` | `>=0.6` | 代码检查和格式检查 |
| `mypy` | `>=1.11` | 静态类型检查 |
| `build` | `>=1.2` | 构建 wheel/发布包 |

开发命令不需要真实凭证，也不会访问真实交易接口。

### 不同功能需要的凭证

- 公共行情接口：不需要凭证；
- 账户、持仓、订单等认证查询：需要 StandX JWT（`access_token`）；
- 下单、撤单、杠杆和保证金模式修改：需要 JWT 加匹配的 32-byte Ed25519 请求签名私钥；
- 钱包登录：需要应用自己实现并注入 `WalletSigner`，SDK 不负责钱包托管。

## 安装

### 从 GitHub 安装

```bash
python -m pip install "git+https://github.com/polibee/standx--python-sdk.git"
```

### 克隆源码开发

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

## 配置凭证

StandX 使用两类凭证：

1. `access_token`：JWT，用于 Bearer 认证和账户查询；
2. `request_signing_key`：匹配的 Ed25519 私钥，用于签名订单和其他签名请求。

API Token 的请求签名私钥由用户自己保管。建议使用环境变量或密钥管理系统，不要提交到 Git：

```python
from standx_sdk import StandXCredentials

credentials = StandXCredentials(
    access_token="<JWT>",
    request_signing_key=StandXCredentials.decode_request_signing_key(
        "<base58或hex或base64私钥>"
    ),
)
```

SDK 支持 base58、hex、base64/base64url，以及 Solana 64-byte secret key 格式（自动使用前
32 bytes）。未知长度不会被静默截断。

只有 JWT 也可以查询账户，但不能完成签名交易：

```python
from standx_sdk import ClientConfig, StandXClient

client = StandXClient(
    ClientConfig(base_url="https://perps.standx.com"),
    access_token="<JWT>",
)
```

## 邀请注册

如果你还没有连接过 StandX 钱包，请在首次连接钱包前打开邀请链接：

<a href="https://standx.com/referral?code=niubiii"><img alt="使用邀请注册链接 StandX" src="https://img.shields.io/badge/%E4%BD%BF%E7%94%A8%E9%82%80%E8%AF%B7%E6%B3%A8%E5%86%8C%20StandX-niubiii-2563eb?style=for-the-badge&labelColor=111827"></a>

邀请码属于官方网页注册流程，不是 REST 下单参数。SDK 不会把邀请码加入认证或交易请求。
已经使用过 StandX 的钱包是否可以补绑邀请码，应以 StandX 当前网页规则为准，SDK 不假设
邀请码可以事后添加。

## 查询特定交易对行情

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
        print("最新价:", price.last_price)
        print("标记价:", market.mark_price)
        print("买盘/卖盘:", depth.bids, depth.asks)
        print("最小下单量:", rules.min_order_qty)
        print("成交数量:", len(trades), "K线数量:", len(candles.bars))


asyncio.run(main())
```

已实现的行情 REST 方法包括：`overview()`、`symbol_price()`、`symbol_market()`、
`depth_book()`、`recent_trades()`、`symbol_info()`、`kline_history()`、`server_time()`、
`health()`。

## 实时行情

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

用户频道包括 `order`、`position`、`balance`、`trade`。订阅前需要调用：

```python
await stream.authenticate(token, streams=["order", "position"])
```

## 签名交易

```python
from decimal import Decimal
from standx_sdk import ClientConfig, StandXClient, StandXCredentials
from standx_sdk.models.order import CreateOrderRequest, OrderSide, OrderType, TimeInForce


async def trade() -> None:
    credentials = StandXCredentials(
        access_token="<JWT>",
        request_signing_key=StandXCredentials.decode_request_signing_key("<私钥>"),
    )
    async with StandXClient(
        ClientConfig(base_url="https://perps.standx.com"),
        credentials=credentials,
    ) as client:
        rules = await client.markets.symbol_info("BTC-USD")
        order = CreateOrderRequest(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            qty=Decimal("0.1"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            cl_ord_id="example-order-001",
        )
        submission = await client.orders.create(order, rules=rules)
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

创建 Order Response Stream 后，SDK 会自动把 `session_id` 设置到共享 REST transport 的
`x-session-id`。REST 返回 `accepted` 只表示网关接受请求，不代表最终成交或撤单完成；最终
状态应通过用户订单流或 REST 查询确认。超时和断线不会自动重放订单请求。

## PAPER 和 LIVE

```python
from standx_sdk import ClientConfig, Environment

paper = ClientConfig(
    base_url="https://perps.standx.com",
    environment=Environment.PAPER,
)

# LIVE 必须由应用显式选择。
live = ClientConfig(
    base_url="https://perps.standx.com",
    environment=Environment.LIVE,
)
```

SDK 不会自动推断 LIVE 凭证、不保存私钥，也不实现钱包资金操作。交易机器人建议只开启
API Token 的 `Trade` 权限并关闭 `Withdraw` 权限。

## 错误诊断

`StandXError.code` 是稳定且适合程序判断的错误码：`401` 映射为 `AUTH_FAILED`，`403` 映射为
`PERMISSION_DENIED`，`404` 映射为 `NOT_FOUND`（检查认证环境、接口版本、域名或凭证类型），
`5xx` 映射为 `SERVER_ERROR`。`retryable` 表示是否可以考虑重试。网络失败时，
`transport_error_type` 会提供脱敏后的原因，例如 `DNS error`、`TLS error`、`ProxyError`、
`ConnectTimeout`、`ReadTimeout` 或 `RemoteDisconnect`。错误信息不会包含 JWT、私钥、认证头、
URL 或完整底层异常文本。

```python
try:
    await client.markets.overview()
except StandXError as exc:
    print(exc.code, exc.retryable, exc.transport_error_type)
```

## 开发和验证

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
```

`tools/verify_credentials.py` 可以使用被 `.gitignore` 忽略的本地 `.env` 做 PAPER 只读验证，
不会下单，也不会执行钱包操作。

## 文档

- [English README](README.md)
- [SDK 设计文档](docs/standx-sdk-design.md)
- [可移植 SDK 通用设计文档](docs/standx-sdk-portable-design.md)
- [StandX 协议整理](docs/standx.md)
- [更新日志](CHANGELOG.md)
- [StandX 官方认证文档](https://docs.standx.com/standx-api/perps-auth)
- [StandX 官方 API Token 文档](https://docs.standx.com/docs/standx-perps-solutions/api-token)

## 基础设施推荐

以下是可选的基础设施推荐链接，不是 SDK 的依赖：

- [使用 Vast.ai 部署](https://cloud.vast.ai/?ref_id=91181)
- [![DigitalOcean Referral Badge](https://web-platforms.sfo2.cdn.digitaloceanspaces.com/WWW/Badge%201.svg)](https://www.digitalocean.com/?refcode=497113351f20&utm_campaign=Referral_Invite&utm_medium=Referral_Program&utm_source=badge)

## 安全说明

JWT、Ed25519 私钥和签名必须留在应用自己的密钥管理边界内。PAPER 测试不等于 LIVE 交易
就绪；部署自动化交易前，请确认权限、限流、风控、监控和异常恢复策略。
