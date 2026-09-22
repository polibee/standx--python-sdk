# StandX Python SDK 设计说明

## 1. 文档状态

- 状态：设计评审中
- 目标：在本仓库实现独立、可复用、可测试的 StandX Python SDK
- 范围：只实现 Python SDK
- 不在范围内：Go SDK、`StandXAdapter`、交易机器人运行时、真实账户交易验证
- 默认运行模式：PAPER/测试环境
- LIVE：必须由调用方显式启用，且不属于本阶段的真实交易验收范围

## 2. 背景与目标

当前仓库只有 StandX 协议和 SDK 架构文档，没有可运行的 Python 包、测试套件或发布配置。本项目将从零构建 Python SDK，把认证、请求签名、REST、WebSocket、重试、限流、错误转换和测试工具放在独立模块中。

SDK 的目标是让业务代码依赖稳定的 Python DTO 和服务接口，而不是依赖 StandX 原始 JSON、HTTP 实现细节或 WebSocket 连接状态。

核心目标：

1. 提供明确的 Python 公共 API。
2. 支持 BSC/EVM 和 Solana/SVM 登录签名能力注入。
3. 支持 JWT 认证及请求体签名。
4. 提供市场、账户、余额、持仓和订单 REST API。
5. 提供市场流、用户流和异步订单响应流。
6. 支持心跳、断线重连和订阅恢复。
7. 对订单超时和未知状态采取安全的 fail-closed 语义。
8. 使用 Fake REST/WebSocket Server 和固定测试向量进行离线验证。
9. 不在 SDK 内保存私钥，不在测试中使用真实账户或真实交易。

## 3. 非目标

以下内容不由本项目实现：

- Go SDK；
- 交易机器人 `StandXAdapter`；
- Exchange Registry 注册；
- 策略、风控、仓位管理和订单执行编排；
- 私钥托管、钱包创建或密钥持久化；
- 真实 LIVE 账户连接证明；
- 真实资金、真实订单和真实交易验证；
- 与交易机器人仓库的直接耦合。

## 4. 设计原则

### 4.1 协议与业务隔离

SDK 内部负责 HTTP/WebSocket 协议、认证、签名和重连；调用方只接触 DTO、请求对象、流事件和统一异常。

### 4.2 依赖注入

钱包签名器、HTTP 传输、WebSocket 传输和时钟都应可替换。认证和签名测试不得依赖真实钱包或网络。

### 4.3 安全默认值

默认使用 PAPER。LIVE 必须显式配置。SDK 不接收需要长期保存的私钥，也不把认证 token、签名、私钥或完整敏感请求体写入普通日志。

### 4.4 订单状态优先于请求结果

网络超时只表示请求结果未知，不表示订单失败。对可能产生外部副作用的请求，不进行无幂等键的自动重试。

### 4.5 可独立验证

每个阶段都必须有独立测试和可审查的提交边界；所有协议关键行为优先使用 Fake Server、mock transport 或固定向量验证。

## 5. 公共 API 草案

### 5.1 客户端初始化

```python
from standx_sdk import ClientConfig, Environment, StandXClient

client = StandXClient(
    config=ClientConfig(
        base_url="https://api.standx.com",
        environment=Environment.PAPER,
    ),
    signer=signer,
)
```

`ClientConfig`至少包含：

- `base_url`；
- `auth_base_url`、`market_stream_url`和`order_response_url`；
- `environment`；
- 请求超时配置；
- 重试策略配置；
- 限流配置；
- 可选的 `impersonated_vault_id`；
- 可注入的 HTTP/WebSocket transport。

`StandXClient`接受可选的 `request_signer`和 `http_transport`，所有 REST domain service 共享同一个实例；WebSocket endpoint 从 `ClientConfig`读取，不能在 facade 内硬编码。`client.streams.market(transport=...)`和 `client.streams.order_response(transport=...)`支持注入 Fake WebSocket transport。这样请求签名、Fake HTTP/WebSocket transport 都可以在离线测试和 PAPER 环境中替换真实网络实现。

`AuthService.login()`成功后会通过 token sink 更新共享 REST transport 的 Bearer token，因此后续账户、订单和市场请求使用同一个认证状态。`StandXClient.close_async()`负责关闭已创建的 stream、REST transport 和认证 transport；该方法幂等，`StandXClient`也支持 `async with`，退出上下文时自动释放资源。关闭后的 client 不允许再创建 stream。

`StandXClient.positions`和`StandXClient.trades`是面向领域的类型化服务视图，复用同一个 `AccountApi`和 HTTP transport；它们不创建新的认证或网络状态，也不暴露原始 REST JSON。`market_stream()`和`order_response_stream()`是 `streams` 工厂的直接便捷入口，创建的 stream 仍由同一个 registry 负责关闭。

### 5.2 服务入口

```python
await client.auth.login()
markets = await client.markets.list()
account = await client.account.snapshot()
positions = await client.positions.list()
order = await client.orders.create(create_request)
await client.orders.cancel(order_id, client_order_id=client_order_id)

market_stream = client.streams.market()
order_stream = client.streams.order_response()
```

服务入口只暴露类型化请求和响应，不暴露 REST 原始 JSON。账户和市场 domain 内部的 `_balance_raw()`、`_positions_raw()`、`_trades_raw()`、`_funding_rates_raw()`和`_recent_trades_raw()`仅用于 DTO 映射，不属于公共调用入口。

## 6. 模块结构

目标包结构（现代公共结构）：

```text
src/standx_sdk/
├── __init__.py
├── client.py
├── config.py
├── domain/
│   ├── __init__.py
│   ├── markets.py
│   ├── account.py
│   ├── orders.py
│   └── trades.py
├── streams/
│   ├── __init__.py
│   ├── base.py
│   ├── market.py
│   └── order_response.py
├── transport/
│   ├── __init__.py
│   ├── http.py
│   └── websocket.py
├── auth/
│   ├── __init__.py
│   ├── service.py
│   ├── token.py
│   └── wallet.py
├── signing/
│   ├── request.py
│   └── encoding.py
├── models/
│   ├── common.py
│   ├── market.py
│   ├── account.py
│   ├── order.py
│   ├── trade.py
│   └── stream.py
├── errors/
│   ├── __init__.py
│   ├── codes.py
│   └── exceptions.py
├── resilience/
│   ├── retry.py
│   └── rate_limit.py
└── testing/
    ├── fake_http.py
    ├── fake_websocket.py
    └── fixtures/
```

旧的 `rest/` 和 `websocket/` 实现不保留；新的公共扩展边界只有 `domain/`、`transport/` 和 `streams/`。模块职责必须保持单一：`client.py`只负责组合依赖，`domain/`负责 StandX endpoint，`transport/`负责网络协议，`streams/`负责连接生命周期，公共 DTO 不依赖 HTTP/WebSocket 客户端实现。

## 7. 认证与签名

### 7.1 登录流程

认证流程固定为：

1. 生成临时 ed25519 key pair 和 base58 request ID。
2. 调用 `prepare-signin`。
3. 解析服务端返回的 `signedData` JWT payload。
4. 使用注入的 EVM 或 Solana 钱包签名器签名 `payload.message`。
5. 调用 `login` 获取访问 token。
6. 保存 token 的内存态和过期时间，不保存钱包私钥。

### 7.2 签名接口

```python
class WalletSigner(Protocol):
    chain: Chain
    address: str

    async def sign_login_message(self, message: str) -> str: ...


class RequestSigner(Protocol):
    def sign_request(
        self,
        version: str,
        request_id: str,
        timestamp: int,
        payload: str,
    ) -> str: ...
```

请求签名消息格式必须为：

```text
{version},{request_id},{timestamp},{payload}
```

签名结果使用 Base64 编码，并生成：

```text
x-request-sign-version
x-request-id
x-request-timestamp
x-request-signature
```

### 7.3 JWT 与 token

- JWT payload 只用于读取过期时间和登录响应字段；登录成功后 `AuthService.token_expires_at` 仅在内存保存整数 `exp`，`is_token_expired()`用于本地判断；
- SDK 不把 JWT 当作可自行信任的授权证明；
- token 缺失、过期或服务端拒绝时转换为统一错误；
- 不在错误消息中打印 token 原文。

`AuthService` 对服务端拒绝返回 `AUTH_FAILED`，对缺失或非法 `signedData`、非对象 JWT payload、缺失或类型错误的登录认证字段返回不可重试的 `PROTOCOL_ERROR`；错误消息只包含固定诊断文本，不回显 JWT、签名或完整认证请求体。

登录成功后，`StandXClient` 将 token 和解析出的 JWT `exp` 同步到共享 REST transport。每次请求
在访问网络前检查过期时间，已过期时直接返回不可重试的 `TOKEN_EXPIRED`；SDK 不自动刷新 token，
调用方必须重新登录。opaque token 没有可解析的 `exp` 时保持兼容，不做本地过期判断。

`expires_seconds` 必须是正整数，SDK 在发出认证请求前拒绝零、负数、布尔值和浮点值。

### 7.4 数值 DTO 边界

文档中的金额、价格、数量、费率、深度和成交量字段统一映射为有限 `Decimal`。服务端返回
`NaN`、`Infinity`、`-Infinity` 或其他无法解析的数值时，REST DTO 和 Market Stream DTO
必须返回不可重试的 `PROTOCOL_ERROR`，不得把非有限值交给订单校验、缓存或状态恢复逻辑。

## 8. REST 设计

REST 分层如下：

```text
RestTransport
    ├── AuthApi
    ├── MarketsApi
    ├── AccountApi
    ├── PositionsApi
    └── OrdersApi
```

账户、市场和订单查询使用类型化 DTO：`BalanceSnapshot`、`PositionSnapshot`、`MarketOverview`、`SymbolMarket`、`SymbolPrice`、`DepthBook` 和 `Order`。这些 DTO 对文档中的 decimal 字段统一使用 `Decimal`，`InstrumentRules`覆盖启用状态和创建/更新时间，`SymbolMarket`覆盖 `base`、`quote`和`spread`，`SymbolPrice`覆盖 `base`和`quote`；`PositionSnapshot`覆盖清算价、保证金、持仓价值、维持保证金率和标记价等文档字段，`Order`覆盖锁定金额、区块、仓位、来源和时间等查询字段；订单 `status` 保留 StandX 原始字符串（包括示例中的 `new`），不会把服务端状态擅自改写为其他交易所状态。

`MarketsApi.overview()`、`symbol_market()`、`symbol_price()`和`depth_book()`分别对应 StandX 的市场概览、标的行情、标的价格和深度接口；深度 asks/bids 保持服务端顺序，不在 SDK 内隐式排序。`AccountApi.trade_snapshots()`和`funding_history()`分别映射用户成交与资金历史，手续费、成交价值、PnL 和资金费用均按文档使用 `Decimal`。

### 8.1 Transport 职责

- 构造 URL；
- 添加认证头和请求 ID；
- 对需要签名的 body 使用稳定 JSON 序列化；
- 解析 HTTP 响应；
- 映射超时、连接错误、HTTP 错误和 JSON 错误；
- 记录脱敏诊断信息。

`HttpTransport`使用 `ClientConfig.timeout_seconds`创建 `httpx.AsyncClient`。网络超时映射为可重试的 `REQUEST_TIMEOUT`；HTTP 400/401/403/408/429/5xx分别映射为验证、认证、超时、限流或协议错误，并尽可能保留响应中的 `message`、`x-request-id`/`request_id`和非负有限的 `retry-after` 秒数。非法、负数或非有限 `retry-after` 会被忽略，不会覆盖原本的 `RATE_LIMITED`/其他 HTTP 错误。`aclose()`幂等；关闭后的请求统一返回不可重试的 `PROTOCOL_ERROR`，不泄漏底层 httpx 生命周期异常。

HTTP 连接失败映射为可重试的 `PROTOCOL_ERROR`，不把底层 URL、Authorization 或请求体写入错误消息。

创建订单、单笔撤单和批量撤单的 HTTP 超时会转换为不可自动重试的 `ORDER_UNKNOWN`，调用方必须先按订单标识查询或通过 Order Response Stream 确认再决定后续动作；其他 REST 成功响应的非法 JSON 统一转换为不可重试的 `PROTOCOL_ERROR`。

REST 成功响应的 DTO 映射也属于协议边界：市场接口的缺失必填字段、空规则列表、非法整数/Decimal、损坏的深度层级或错误的成交数组结构，以及账户、持仓、配置、成交、资金历史和订单查询/提交/撤单的缺失字段或非法数值，统一转换为不可重试的 `StandXError(code=PROTOCOL_ERROR)`。错误消息只包含 endpoint 标识，不包含原始响应、认证头或请求参数；底层已产生的 `StandXError` 不会被二次包装。

### 8.2 API 服务职责

各 API 服务负责 endpoint 路径、请求 DTO、响应 DTO 和业务级错误判断。它们不得直接操作底层 HTTP 库的异常类型。

### 8.3 订单安全规则

- `cl_ord_id`按 StandX 文档为可选，服务端会自动生成；SDK 默认生成并发送客户端 ID 以便恢复状态，但必须保留服务端返回值；
- 创建订单超时返回 `ORDER_UNKNOWN`；
- 只有服务端明确拒绝时才能返回 `ORDER_REJECTED`；
- 对创建订单不默认自动重试；
- 支持通过 `client_order_id`查询恢复状态；
- `OrdersApi.query_order()`、`query_orders()`和`query_open_orders()`用于恢复和读取订单快照；
- 撤单请求需要区分“发送成功”和“最终状态确认”。

### 8.4 StandX 市场规则与订单精度

StandX 的 `GET /api/query_symbol_info` 返回交易标的规则。SDK 必须以该响应为依据构造并缓存 `InstrumentRules`，不能凭通用交易所经验推导规则。

```python
@dataclass(frozen=True)
class InstrumentRules:
    symbol: str
    base_asset: str
    base_decimals: int
    quote_asset: str
    quote_decimals: int
    price_tick_decimals: int
    qty_tick_decimals: int
    min_order_qty: Decimal
    max_order_qty: Decimal
    max_position_size: Decimal
    max_leverage: int
    def_leverage: int
    max_open_orders: int
    price_cap_ratio: Decimal
    price_floor_ratio: Decimal
    maker_fee: Decimal
    taker_fee: Decimal
    depth_ticks: tuple[Decimal, ...]
```

上述字段对应 StandX `query_symbol_info` 文档中的 `min_order_qty`、`max_order_qty`、`max_position_size`、`price_tick_decimals`、`max_leverage`等字段。`minimum_notional`、`quantity_step`、`post_only`等当前本地文档和官方参考页未定义，首版不得虚构为 StandX 能力。

校验顺序：

1. `symbol`必须存在且已加载对应市场规则。
2. 数量和价格必须使用 `Decimal`解析，禁止使用二进制浮点数参与精度判断。
3. 数量必须大于零，且满足 `min_order_qty <= qty <= max_order_qty`。
4. 持仓相关的数量不得超过 `max_position_size`；`reduce_only`还必须遵守 StandX 文档给出的可减少仓位公式。
5. 限价订单价格必须按 `price_tick_decimals`序列化；官方文档要求 decimal 参数使用 JSON 字符串，禁止 JSON 浮点数。
6. 杠杆不得超过 `max_leverage`，且必须使用整数。
7. 价格上下限按服务端公布的 `price_cap_ratio`和 `price_floor_ratio`执行；若公式未在协议文档中明确，SDK 不自行推导，只保留服务端错误。
8. 通过已确认的本地校验后，才允许序列化和发送请求。

`OrdersApi.create()`接受可选的 `InstrumentRules`、`position_qty`和`pending_reduce_only_qty`，调用 `validation.validate_order()`执行上述本地校验。由 `StandXClient` 创建的 `OrdersApi` 在未显式提供规则时，会通过 `MarketsApi.symbol_info()` 查询并缓存当前标的规则，再执行本地校验；规则查询失败或规则校验失败都不会发送下单请求。直接构造 `OrdersApi` 时可注入 `rules_provider`，未注入时仍要求调用方显式提供规则，不猜测市场限制。

默认行为是拒绝不符合数量或价格精度的输入，而不是静默四舍五入。数量使用 `qty_tick_decimals`，价格使用 `price_tick_decimals`。数量、价格、`tp_price`和`sl_price`还必须是有限正数，不能使用 `NaN` 或无穷值。`OrdersApi.create()`可接收 `position_leverage` 和 `position_margin_mode` 对当前配置做匹配校验；不传这些当前状态时，SDK 不会自行修改账户配置。`tp_price`和`sl_price`必须为正数，并按 `price_tick_decimals` 校验精度；SDK 不推断止盈止损方向关系。若未来提供显式的量化辅助方法，也必须返回新的订单值并由调用方明确选择，不得在 `orders.create()`内部隐式修改用户订单。

```python
class OrderValidationError(StandXError):
    code = ErrorCode.VALIDATION_ERROR
    field: str
    value: str
    rule: str
```

错误信息至少指出字段、实际值和违反的规则，例如数量不满足步长、价格超过精度或名义价值低于最小值。服务端最终校验仍然有效，SDK 本地校验不能被视为服务端接受保证。

`MarketsApi.symbol_info()`会缓存成功解析的 `InstrumentRules`；同一标的的并发首次加载共享一个 in-flight REST 请求，不同标的仍可并发。传入 `refresh=True`可强制重新查询，`clear_symbol_info_cache(symbol=None)`可清理单个标的或全部缓存。只有成功完成 DTO 映射的结果才会写入缓存；规则查询失败时不会污染已有缓存，订单调用方可显式刷新后再进行本地校验。订单创建前如果规则不存在或已过期，SDK 应先刷新规则；刷新失败时拒绝创建订单，不使用过期规则猜测是否可以下单。

### 8.5 杠杆、保证金和持仓语义

杠杆不是订单字段的简单别名，必须作为独立的账户/标的配置能力设计：

```python
class MarginMode(str, Enum):
    CROSS = "cross"
    ISOLATED = "isolated"


@dataclass(frozen=True)
class PositionConfig:
    symbol: str
    leverage: int
    margin_mode: MarginMode


@dataclass(frozen=True)
class ConfigChangeResult:
    code: int
    message: str
    request_id: str
```

SDK 必须区分：

- 查询当前杠杆和保证金模式；
- 查询标的允许的最大杠杆；
- 设置杠杆；
- 设置杠杆后再创建订单；
- 服务端拒绝设置杠杆；
- 设置成功但本地缓存尚未刷新。

当前实现提供 `AccountApi.position_config_snapshot(symbol)` 返回
`PositionConfig`，以及 `change_leverage_config(symbol, leverage)` 和
`change_margin_mode_config(symbol, margin_mode)` 返回 `ConfigChangeResult`。
两个变更方法只表示服务端接受了配置请求，并不代表已有持仓或订单已经改变；
调用方应重新查询 `position_config_snapshot`确认最终账户配置。配置变更是有副作用
的 POST，SDK 默认不自动重试，也不会在创建订单时静默修改账户配置。

设置杠杆属于有外部副作用的操作，默认不自动重试。创建订单前，如果请求指定的杠杆、保证金模式或持仓模式与当前账户状态不一致，SDK 必须拒绝请求或要求调用方显式确认，不得自动修改账户配置。

当前 `docs/standx.md`没有定义单向/双向持仓或 `position_side`字段，因此首版不设计 `PositionMode`公共参数；订单只使用 StandX 已确认的 `side`和 `reduce_only`。

### 8.6 StandX 订单类型和执行指令

官方参考目前定义的订单类型只有 `limit`和 `market`，时间指令只有 `gtc`、`ioc`和 `alo`：

```python
class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    ALO = "alo"


@dataclass(frozen=True)
class CreateOrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    client_order_id: str | None = None
    price: Decimal | None = None
    time_in_force: TimeInForce
    reduce_only: bool
    margin_mode: MarginMode | None = None
    leverage: int | None = None
    tp_price: Decimal | None = None
    sl_price: Decimal | None = None
```

参数约束：

- `MARKET`订单不能要求 `price`；
- `LIMIT`订单必须有 `price`；
- `time_in_force`必须是 `gtc`、`ioc`或 `alo`；
- `alo`是 StandX 文档定义的 Add Liquidity Only 语义，对应此前泛称的 post-only，但公共 DTO 使用 `TimeInForce.ALO`，不再虚构 `post_only`请求字段；
- `reduce_only=True`时，最大数量是“当前持仓数量 - 其他待处理 reduce-only 订单累计数量”，其中包括 TP/SL 订单；
- `margin_mode`必须与当前持仓匹配；
- `leverage`是 StandX 请求中的整数，必须与当前持仓/配置匹配；
- `tp_price`和 `sl_price`是 StandX 官方订单参数，订单成交后创建对应 TP/SL 订单；
- 官方文档未定义 FOK、STOP_MARKET、STOP_LIMIT、独立 `post_only`字段，首版不加入这些公共参数。

SDK 不默认补充 `time_in_force`，不把限价单变成市价单，也不把 `alo`、`reduce_only`或 TP/SL 语义转换成别的请求字段。

### 8.7 成交属性与费用

StandX 当前公开接口没有在 `new_order`请求中提供 maker/taker 参数。公开 `query_recent_trades`返回 `is_buyer_taker`，用户成交返回 `fee_asset`和 `fee_qty`：

- `MarketsApi.recent_trades()`保留文档原始响应；`recent_trade_snapshots()`映射为 `RecentTrade`，将`price`、`qty`和`quote_qty`转换为 `Decimal`，并原样保留 `is_buyer_taker`；
- `AccountApi.funding_rates()`保留原始查询结果；`funding_rate_snapshots()`映射文档定义的 `FundingRate`，将费率、溢价、指数价和标记价转换为 `Decimal`；
- `AccountApi.trades()`/`trade_snapshots()`支持文档定义的 `last_id`、`side`、`start`、`end`和`limit`；`funding_history()`支持 `start`、`end`、`last_id`和`limit`，未提供的参数不会发送；
- `alo`是 StandX 文档定义的只加流动性时间指令；
- 订单是否成交、成交价和成交量由订单/交易响应确认；
- `is_buyer_taker`只能在 recent trades DTO 中按原字段暴露；
- 用户成交 DTO 应记录 `fee_asset`、`fee_qty`、`price`、`qty`、`value`和 `order_id`；
- SDK 不根据订单类型猜测 maker/taker，也不把 `maker_fee`推导成某笔成交的最终手续费。

### 8.8 StandX 订单状态与异步响应

StandX 官方参考定义的订单状态为 `open`、`canceled`、`filled`、`rejected`、`untriggered`。查询接口示例还出现 `new`，因此 SDK 必须保留原始状态字符串，并以协议契约测试实际返回值；不能擅自改名为通用交易所状态。

```text
HTTP_SUBMITTED
    ├── OPEN
    ├── FILLED
    ├── CANCELED
    ├── REJECTED
    └── UNTRIGGERED

HTTP_SUBMITTED ────> UNKNOWN   (请求提交后无法确认异步结果)
OPEN ───────────────> UNKNOWN   (状态事件丢失且查询失败)
```

状态规则：

- `filled`、`canceled`、`rejected`是官方已定义的终态；
- `untriggered`必须保留，不能当作 `open`；
- `fill_qty`和 `qty`用于计算已成交量和剩余量，但不能凭此虚构 `partially_filled`服务端状态；
- `UNKNOWN`是 SDK 的本地通信状态，不是 StandX 服务端订单状态；
- `new_order`和 `cancel_order`的 HTTP 成功只代表请求提交/接受，不代表撮合或撤单最终完成；
- `x-session-id`必须与 Order Response Stream 的 WebSocket `session_id`一致；
- 订单响应流通过 `request_id`关联请求；request ID 必须非空，仍处于 pending 的 ID 不得复用；缺少或非法响应 envelope 不能清理 pending 状态。用户订单流通过 `id`、`cl_ord_id`和 `updated_at`更新 DTO；
- 订单恢复必须通过 `/api/query_order`或 `/api/query_orders`重新查询；
- 重启后不能依赖进程内状态，必须允许从 REST 快照重建。

`restore_open_orders()` 和 pending request 恢复复用每个 `cl_ord_id` 的刷新锁，并通过同一快照
新鲜度门槛合并缓存；恢复查询不会用较旧的 open-order 列表覆盖并发期间已经观察到的更新订单。

订单 DTO 至少包含：

- 服务端 `order_id`；
- `client_order_id`；
- symbol、side、order type；
- requested quantity、filled quantity、remaining quantity；
- average fill price；
- limit price；
- time-in-force；
- reduce-only；
- TP/SL trigger prices；
- fee、fee asset；
- 当前统一状态；
- 服务端原始状态；
- 创建和更新时间。

## 8.9 StandX 能力边界

本设计以官方文档为准，首版只承诺以下已确认能力：

| 能力 | StandX 文档依据 | 首版处理 |
|---|---|---|
| limit/market | API Reference | 支持 |
| gtc/ioc/alo | API Reference | 支持 |
| reduce_only | `new_order` | 支持并实现待处理 reduce-only 数量校验 |
| leverage | `change_leverage`、`query_position_config` | 支持整数杠杆 |
| margin_mode | `change_margin_mode`、`query_position_config` | 支持 `cross`/`isolated` |
| tp_price/sl_price | `new_order` | 支持原始字段和成交后订单说明 |
| qty_tick_decimals | `query_symbol_info` | 支持数量精度校验 |
| price_tick_decimals | `query_symbol_info` | 支持价格精度校验 |
| min/max_order_qty | `query_symbol_info` | 支持数量范围校验 |
| max_position_size | `query_symbol_info` | 支持持仓上限校验 |
| maker_fee/taker_fee | `query_symbol_info` | 建模为费率元数据，不推断单笔成交角色 |
| FOK | 当前参考未定义 | 不加入首版 |
| 独立 post_only | 当前参考未定义；使用 `alo` | 不加入独立字段 |
| STOP_MARKET/STOP_LIMIT | 当前参考未定义 | 不加入首版 |
| maker/taker订单字段 | 当前 HTTP new_order 未定义 | 不在订单请求中加入；按成交数据原样建模 |

## 9. StandX WebSocket 设计

本地 `docs/standx.md` 明确规定 StandX 只有两个 WebSocket 入口：

```text
Market Stream:  wss://perps.standx.com/ws-stream/v1
Order Response: wss://perps.standx.com/ws-api/v1
```

不能把用户事件设计成第三个连接。Market Stream 同时承载公开市场 channel 和认证后的用户 channel；Order Response Stream 专门承载 `order:new`、`order:cancel`的异步响应。

公共连接管理器负责：

- 连接建立和关闭；
- 心跳；
- 读写任务；
- 连接超时；
- 指数退避重连；
- 订阅注册表；
- 重连后的订阅恢复；
- 消息协议验证。

Market Stream 的已确认 channel 为：

- 公开：`price`、`depth_book`、`public_trade`，需要 `symbol`；
- 用户：`order`、`position`、`balance`、`trade`，需要 JWT 认证。

SDK 将 Market Stream 的 `data` 映射为 `models.stream` 中的不可变 DTO：

- `order` → `UserOrderEvent`：保留服务端 `status` 原文，数量、价格和成交字段使用 `Decimal`；
- `position` → `PositionEvent`：`qty` 使用 `Decimal`，`leverage` 使用整数；
- `balance` → `BalanceEvent`：余额字段使用 `Decimal`；
- `trade` → `UserTradeEvent`，公开 `price`、`depth_book`、`public_trade` 也有对应 DTO；
- 未知 channel 转换为 `ValueError`；非对象 envelope、缺少 `channel`/`data`、缺失 DTO 必填字段、非法 Decimal 或损坏层级结构统一转换为 `StandXError(code=PROTOCOL_ERROR)`。

用户事件不会被拆成第三条 WebSocket 连接，仍由 Market Stream 统一承载。所有 Market Stream DTO 都保留消息顶层 `seq`，且非整数 `seq`按协议错误拒绝；`UserOrderEvent`保留订单 channel 文档定义的锁定金额、保证金、仓位、来源、区块和时间字段；`PositionEvent`和`BalanceEvent`保留文档定义的保证金、钱包、交易和账户元数据；`PriceEvent`保留文档定义的 `base`、`quote`和`time`；DTO 映射只做类型转换，不推导 maker/taker、部分成交状态或其他 StandX 未定义字段。

订单恢复按 `cl_ord_id` 维护 `updated_at` 事件水位。早于已处理水位的用户事件不会再次触发 REST 查询；
REST 返回的订单快照如果早于当前事件，也不会覆盖本地缓存。缺少或无法解析时间戳时保持兼容，仍以
REST 快照为权威，不凭局部用户事件字段拼装订单状态。

Market Stream 的用户 channel 必须先调用 `authenticate(token, impersonate=..., streams=...)`。SDK 发送文档定义的 `{ "auth": { "token": ..., "impersonate": ..., "streams": [{"channel": ...}] } }` 消息，并且只有收到 `channel=auth` 且 `data.code=200` 后才允许订阅 `order`、`position`、`balance`或`trade`；`streams`只能包含这四类用户 channel。重连时会先使用原认证参数重新认证，再按原顺序恢复用户订阅；连接或认证失败都会清除本地已认证状态，不会伪造认证成功。服务端使用 JSON 整数错误码拒绝认证时统一为 `StandXError(code=AUTH_FAILED)`；认证响应缺少 `code` 或 code 不是 JSON 整数时统一为 `PROTOCOL_ERROR`。

Depth book 的 asks/bids 顺序不保证，SDK 不能默认假定已排序。`WebSocketTransport` 默认启用客户端 Ping/Pong（`ping_interval=20s`、`ping_timeout=60s`），由底层 websockets 连接负责无响应检测；调用方可以显式传入 `None`关闭某项或调整参数，但启用的参数必须是有限正数。连接层还必须处理服务端 Ping/Pong、5 分钟未收到 Pong 的断开，以及单连接最长 24 小时的生命周期。

Order Response Stream 请求必须严格使用 `session_id`、`request_id`、`method`、`header`、JSON 字符串形式的 `params`。HTTP `new_order`和 `cancel_order`的 `x-session-id`必须与 WebSocket 的 `session_id`一致。响应需要区分 `accepted`、成功和拒绝；`accepted`只表示网关接受处理，不表示已经成交或撤单完成。

`OrderResponseStream.authenticate()`封装文档定义的 `auth:login` 请求，验证非空 token，保留
`session_id + request_id` pending 关联，并返回解码后的 `OrderResponseEvent`；连接断开时不会自动
重发认证请求。

订单列表 REST 响应必须是包含数组 `result` 的对象；订单提交响应的 `code` 必须是 JSON 整数，
`message`、`request_id` 和可选 `cl_ord_id` 必须是字符串。违反这些类型契约统一返回不可重试的
`PROTOCOL_ERROR`，不向公共 API 泄漏原生类型异常。

`OrderResponseStream.decode_response()`将文档中的响应映射为 `OrderResponseEvent`：`status=accepted`映射为 `accepted`，`code=0`且无 accepted 状态映射为 `success`，`code>=400`映射为 `rejected`，其他情况保留为 `unknown`。解码后只清理对应的 pending request，不会把断线中的 `order:new`或`order:cancel`重新发送，避免产生重复外部副作用。

Order Response 响应缺少 `request_id`、session 不匹配、缺少 `code` 或 `code` 不是 JSON 整数时，必须统一转换为 `StandXError(code=PROTOCOL_ERROR)`，并在可识别时保留 `request_id`；不能向公共 API 泄漏原生 JSON/类型转换异常。

订单响应流必须使用 `session_id + request_id`做关联，不能只使用单一 request ID。断线期间未确认的请求不能自动判定为成功或失败，应进入本地未知状态并由 REST 查询恢复。如果响应包含 `session_id`，必须与当前 stream 的 `session_id`一致；不一致统一报 `PROTOCOL_ERROR`，并保留响应中的 `request_id`，且不得清理 pending request。HTTP 错误同时保留服务端原始 `code` 到 `StandXError.server_code`，公共 `code` 仍使用 SDK 稳定错误码。

SDK 的 stream 对象必须只记录已成功发送的 channel，并在连接重建后按原顺序重放订阅；订阅发送失败不得进入恢复列表。调用方显式关闭后不得自动重连。Order Response Stream 必须记录 pending `request_id`，收到响应后移除对应 ID；连接断开时仍 pending 的订单请求保持本地未知状态，不能伪造成功或失败。

Market Stream 订阅恢复失败统一抛出 `StandXError(code=WS_RESUBSCRIBE_FAILED)`，异常链保留底层连接错误，且错误消息包含失败的 channel 和 symbol，便于调用方决定是否重新建连。

连接建立支持注入 sleep 函数的指数退避：默认最多 5 次尝试、初始等待 0.5 秒，每次失败后等待时间翻倍；最后一次失败原样抛出。调用方显式关闭后，连接和重连都会拒绝执行；`connect_with_backoff()`必须立即拒绝且不能调用 sleep 或底层 transport。退避策略不对订单结果做乐观判断，也不会把连接失败转换为订单失败。

Market Stream 与 Order Response Stream 都提供 `connect_with_backoff()`，使用相同的默认退避参数和可注入的 `sleep` 函数；调用方还可以设置 `max_delay` 和 `jitter(delay)`，最终等待时间不会超过 `max_delay`。Order Response Stream 的退避只重试 WebSocket 建连，不会重发 pending 的 `order:new` 或 `order:cancel` 请求。

`standx_sdk.testing.FakeWebSocketServer` 和 `FakeWebSocketTransport` 提供纯内存的双向消息队列，用于离线验证订阅、接收和协议恢复，不访问真实 StandX 网络。

Order Response Stream 会保留 pending 请求的 `method` 与参数。断线恢复时，调用方传入按 `cl_ord_id` 查询 REST 状态的异步函数，SDK 逐个查询拥有客户端订单 ID 的未确认请求，返回查询结果并清理已恢复的 request ID。没有 `cl_ord_id` 的请求不会被猜测成功或失败，继续保持 pending/未知状态。

`OrderStateReconciler`统一处理三类恢复：Order Response Stream 断线后的 pending 请求恢复、Market Stream `order`用户事件后的 REST 重读，以及进程重启后的 `query_open_orders()`缓存重建。用户事件只包含部分字段，不能直接覆盖完整订单；协调器始终按 `cl_ord_id`查询 REST，并把完整的 `Order`快照写入本地缓存。REST 查询不到结果时不写入缓存，也不把订单标记为成功、成交或撤单，pending 请求继续保留，等待后续恢复。重建时没有 `cl_ord_id`的服务端订单会返回给调用方但不会进入可关联缓存。

同一 `cl_ord_id` 的并发用户事件必须串行执行 REST 重读，避免较早发起但较晚返回的查询覆盖后续刷新；不同 `cl_ord_id` 之间保持独立并发。协调器不根据事件局部字段推导状态，也不会因 REST 返回空结果清理已有完整快照。

Order Response Stream 的 pending 恢复也必须复用同一 `cl_ord_id` 锁，并将 REST 查询与完整快照写入作为一个临界区；这样 pending 恢复和用户订单事件重读不会并发覆盖同一订单。

手动关闭必须取消重连任务；发送或接收阶段的底层连接断开或超时必须转换为可重试的 `StandXError(code=WS_DISCONNECTED)`；协议错误必须转换为 `PROTOCOL_ERROR`；恢复订阅失败必须转换为 `WS_RESUBSCRIBE_FAILED`并保留原始诊断上下文。

## 10. 统一错误模型

```python
class ErrorCode(str, Enum):
    AUTH_FAILED = "AUTH_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    RATE_LIMITED = "RATE_LIMITED"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_UNKNOWN = "ORDER_UNKNOWN"
    WS_DISCONNECTED = "WS_DISCONNECTED"
    WS_RESUBSCRIBE_FAILED = "WS_RESUBSCRIBE_FAILED"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
```

统一异常至少包含：

- `code`；
- `message`；
- `request_id`；
- `retryable`；
- 可选的服务端原始错误码；
- 不包含私钥、token 或完整敏感请求体。

## 11. 重试与限流

### 11.1 可重试请求

默认只允许对无副作用或具有明确幂等语义的请求重试，例如读取类 GET、订阅恢复和明确可重放的认证步骤。

创建订单、撤单等副作用请求默认不自动重试。

### 11.2 退避

重试策略需要支持：

- 最大尝试次数；
- 初始延迟；
- 最大延迟；
- 指数退避；
- 抖动；
- 可重试错误码集合。

`RetryPolicy` 只对调用方显式包裹的异步操作生效，并且仅重试 `StandXError.retryable=True`
的错误；如果错误包含合法的 `retry-after`，优先使用该值并受最大延迟限制，否则使用指数退避。
`HttpTransport.get()` 和 `post()` 可通过 `retry_policy=`显式启用。SDK 默认不启用该参数，
因此创建订单、撤单等副作用请求不会被隐式重放；订单创建仍必须在调用方确认幂等性后才可显式包裹。

两个 WebSocket stream 的连接退避也只捕获底层连接类异常；URI、参数和协议错误会立即原样抛出，
不会被重复尝试。初始延迟、最大延迟和 jitter 结果必须是有限且非负的等待时间。

### 11.3 限流

SDK 内置 `CreditRateLimiter`，默认使用 StandX 文档中的每请求 45 credits、每秒补充 1,000 credits、900 credits burst capacity。它在每个 REST 请求前执行 token-bucket 检查；服务端 429 仍然转换为 `RATE_LIMITED` 并保留 `retry-after`。限流器支持注入时钟和 sleep，便于离线确定性测试，也支持调用方替换参数以应对文档未来调整。配置值和单次 cost 必须是有限正数，且 cost 不得超过 capacity；限流不能通过无限等待掩盖调用方错误。

## 12. 测试策略

测试分为四层：

1. 纯单元测试：模型、签名、错误映射、重试和限流。
2. Fake REST 测试：认证、账户、市场、持仓和订单完整请求流程。
3. Fake WebSocket 测试：心跳、断线、重连、恢复订阅和 request/session 关联。
4. PAPER 集成测试：仅在明确配置并具备可用测试环境时运行，默认不依赖真实网络。

必须覆盖：

- 固定 EVM/Solana 登录签名向量；
- 固定 ed25519 请求签名向量；
- token 过期；
- HTTP 错误和非法 JSON；
- 超时与 `ORDER_UNKNOWN`；
- 缺少 `client_order_id`；
- 限流和 retry-after；
- WebSocket 心跳超时；
- 手动关闭不重连；
- 断线后订阅恢复失败；
- session/request 错配；
- 未知字段和协议版本变化；
- 日志脱敏。

禁止测试依赖：

- 真实私钥；
- 真实交易账户；
- 真实下单；
- 未 mock 的外部网络；
- 未声明的环境变量秘密。

## 13. 文档与发布

最终至少提供：

- README 安装和快速开始；
- 认证和签名说明；
- REST API 使用说明；
- WebSocket 流使用说明；
- 错误处理和订单未知状态说明；
- PAPER/LIVE 安全边界说明；
- changelog；
- 版本号和构建配置。

发布前必须通过：

```text
pytest
ruff check .
mypy src
python -m build
```

并完成敏感信息扫描、源码包检查和文档示例检查。

## 14. 分阶段交付

### Phase 0：工程和协议基线

建立 Python 包结构、依赖、错误码、基础 DTO、测试配置和协议测试向量。

### Phase 1：传输、模型和错误

实现配置、HTTP transport、请求 ID、超时、JSON 编解码和统一错误映射。

### Phase 2：认证和签名

实现 `prepare-signin`、JWT 解析、EVM/Solana signer 注入、ed25519 请求签名和 token 管理。

### Phase 3：行情、账户和持仓 REST

实现市场、账户、余额和持仓 API，解析交易标的规则，并完成 DTO 映射和 Fake REST 测试。

### Phase 4：订单和幂等

实现订单创建、查询、撤单、客户端订单 ID、未知状态、Decimal 精度校验、最小/最大订单规则、杠杆/保证金校验、`limit`/`market`、GTC/IOC/ALO、reduce-only、TP/SL 和安全重试策略。

### Phase 5：WebSocket 基础

实现连接管理、心跳、关闭、重连和 Fake WebSocket Server。

### Phase 6：两个 WebSocket 入口与用户 channel

实现 Market Stream 的公开/用户 channel、Order Response Stream、订阅恢复及 `session_id + request_id`关联。

### Phase 7：文档和发布准备

完成 README、示例、Changelog、构建验证、敏感信息扫描和版本发布检查。

### Phase 8：GitHub 推送

在代码和验证完成后初始化 Git，确认远程仓库地址，创建阶段性提交并推送到 GitHub。未确认 remote 前不猜测目标仓库，也不执行推送。

Order Response Stream 的 `request()`和`send_request()`支持调用方注入文档定义的认证 header；请求仍严格保留 `session_id`、`request_id`、`method`、`header`和 JSON 字符串形式的 `params`。

Order Response Stream 的 `order:new`和`order:cancel`必须提供 `x-request-id`、`x-request-timestamp`和`x-request-signature`三项认证 header；`auth:login`可以使用空 header。

其中 `x-request-id`必须与消息 `request_id`一致，`x-request-timestamp`和`x-request-signature`不能为空。

## 15. 验收标准

项目完成必须同时满足：

1. Python SDK 可安装并通过公开入口导入。
2. 认证、REST、WebSocket 都有独立模块和测试。
3. SDK 公共 API 不暴露 REST 原始 JSON。
4. 认证和请求签名有固定向量验证。
5. SDK 默认生成 `cl_ord_id`，同时兼容 StandX 服务端自动生成。
6. 订单数量、价格、数量/价格精度、最小/最大数量和最大持仓量均按 `query_symbol_info`本地校验。
7. 不合规订单不会被 SDK 静默四舍五入或修改。
8. 杠杆、保证金模式和持仓模式不会被 SDK 静默修改。
9. `reduce_only`、TP/SL、margin mode、leverage和 GTC/IOC/ALO组合按 StandX 请求规则校验。
10. `is_buyer_taker`、maker/taker费率和实际手续费不被 SDK 猜测或混淆。
11. 订单状态保留 StandX 原始状态，并额外表达本地异步请求未知状态。
12. 超时订单不会被误判为失败。
13. WebSocket 支持心跳、断线、重连和订阅恢复。
14. Market Stream 与 Order Response Stream 两个入口相互隔离，用户 channel 不被错误拆成第三个连接。
15. 默认不访问真实账户、不执行真实交易。
16. `pytest`、`ruff check .`、`mypy src`和 `python -m build`全部通过。
17. 文档示例、README、安全边界和变更记录完整。
18. GitHub 推送前完成敏感信息检查，并且远程仓库目标明确。
