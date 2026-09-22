# StandX SDK 通用可移植设计文档

> 本文不是某一种语言的实现说明，而是将 StandX Perps SDK 的协议、边界、问题经验和功能设计抽象成可移植规范。Go、TypeScript、Rust、Java、C# 等实现都应以本文和官方协议文档为依据，再映射到本语言的异步、类型系统和错误模型。

## 1. 文档目的和适用范围

目标是设计一个可以安全接入 StandX Perps 的 SDK，覆盖：

- 市场 REST 查询；
- 市场 WebSocket 实时数据；
- JWT 认证；
- Ed25519 请求体签名；
- 账户、持仓、成交和资金费率查询；
- 杠杆和保证金模式配置；
- 下单、查询、撤单、批量撤单；
- 异步订单响应；
- 断线重连、认证恢复和订单状态恢复；
- 限流、错误转换、离线测试和发布。

本文不设计交易策略、交易机器人、风控引擎、钱包 Adapter、链上充值、转账、提现或 Bridge。钱包登录签名只通过抽象接口注入，不在 SDK 内实现私钥托管。

## 2. 已遇到的关键问题

### 2.1 文档不是完整的统一协议

StandX 文档分散在认证、HTTP、WebSocket、API Token 和链特定示例中，存在以下需要特别核对的差异：

- REST endpoint、WebSocket endpoint 和认证 endpoint 不同；
- 有些接口返回顶层数组，有些返回 `{result: [...]}`，不能只实现一种 envelope；
- 订单状态示例同时出现 `open` 和 `new`；SDK 必须保留原始状态，不能擅自统一成其他交易所状态；
- HTTP 下单成功只表示请求提交/网关接受，不表示最终成交；
- Order Response Stream 的 `accepted` 不是最终订单状态；
- 钱包资金操作和合约市场交易接口属于不同边界，不能因为文档列出就全部塞进 SDK；
- 市场规则必须来自 `query_symbol_info`，不能凭经验添加未在文档定义的最小名义价值、数量步长或订单类型。

### 2.2 JWT 和请求签名私钥是两套凭证

JWT 只负责 Bearer 认证。余额、持仓、订单查询等读接口通常只需要 JWT；下单、撤单、批量撤单、杠杆和保证金模式修改等签名 POST 还需要匹配的 Ed25519 请求签名私钥。

这两个凭证不能混淆：

```text
JWT                     -> Authorization: Bearer <token>
Ed25519 request key     -> x-request-sign-* headers
Wallet private key      -> 可选，只用于登录获取 JWT
```

“只有 JWT 能否完成交易”必须明确回答：不能完成要求 body signature 的交易变更；它可以完成允许 JWT 访问的查询。

### 2.3 私钥编码误判

API Token 管理页面允许用户自定义或生成请求签名密钥，文档没有把 UI 导出的编码统一限定为一种格式。实际凭证可能是 base58 字符串。base58 字符串使用的字符集与 base64 有部分重叠，如果先按 base64 解码，一个真实的 32-byte base58 私钥可能被错误解码为 33 bytes。

通用解码顺序建议：

1. 明确长度的 hex：64 个字符代表 32 bytes，128 个字符代表 64 bytes；
2. base58：解码后接受 32 bytes，64 bytes 时按 Solana 约定取前 32 bytes；
3. base64/base64url：解码后接受 32 bytes，64 bytes 时按 Solana 约定取前 32 bytes；
4. 其他长度一律拒绝。

不得因为长度不匹配就任意去掉首字节、尾字节或静默截断。只有官方格式明确说明的包装格式才允许转换。

### 2.4 session_id 需要跨 REST 和 WebSocket 共享

`new_order` 和 `cancel_order` 如果需要接收异步订单结果，REST 请求必须带 `x-session-id`，且这个值必须等于 Order Response Stream 的 WebSocket `session_id`。

常见错误是只在 WebSocket 消息中保存 session ID，却没有把它同步到 REST transport，最终表现为：订单已提交，但客户端收不到对应异步结果。

解决方案是由统一 Client 管理 session binding：创建或切换 Order Response Stream 时，更新共享 REST transport 的 session header。

### 2.5 网络成功不等于业务成功

下列结果必须区分：

```text
HTTP request accepted      -> 网关收到请求
Order Response accepted    -> 网关接受异步处理
Order success/filled       -> 订单业务状态已确认
Order rejected/canceled    -> 订单业务状态已确认失败或撤单
Timeout/disconnect         -> 结果未知，不能当成失败
```

创建订单或撤单超时后自动重试，可能造成重复订单或重复撤单。默认策略必须是返回 `ORDER_UNKNOWN`，由调用方按 `cl_ord_id` 查询或等待订单流恢复。

## 3. 总体架构

推荐分为五层：

```text
Public Client Facade
    ├── Auth Service
    ├── Market Service
    ├── Account / Position / Trade Service
    ├── Order Service
    ├── Market Stream
    └── Order Response Stream

Domain DTO / Validation / Reconciliation

Protocol Transport
    ├── HTTP Transport
    └── WebSocket Transport

Resilience
    ├── Retry Policy
    ├── Credit Rate Limiter
    ├── Reconnect Backoff
    └── Token / Session State

Injected External Boundaries
    ├── Wallet Signer
    ├── Clock
    ├── Sleep
    ├── HTTP Adapter
    └── WebSocket Adapter
```

### 3.1 各层职责

| 层 | 负责 | 不负责 |
|---|---|---|
| Public Client | 组合依赖、暴露稳定入口、统一关闭 | 业务策略、原始网络细节 |
| Domain Service | endpoint、请求 DTO、响应 DTO、领域校验 | 直接操作 HTTP 库 |
| DTO/Validation | 类型转换、精度和规则校验 | 网络重试、连接管理 |
| HTTP Transport | URL、headers、签名、HTTP 错误、JSON | 订单状态推断 |
| WebSocket Stream | 连接、心跳、订阅、消息相关性 | 自动重发有副作用请求 |
| Reconciliation | REST 快照与流事件一致性 | 猜测服务端最终状态 |
| Wallet Signer | 对登录消息签名 | 保存或生成用户钱包 |

### 3.2 公共 Client

所有语言都应提供一个统一入口，概念上至少包含：

```text
client.auth
client.markets
client.account
client.positions
client.trades
client.orders
client.market_stream()
client.order_response_stream(session_id)
client.close()
```

所有 REST domain service 应共享同一个认证状态、签名器、限流器、HTTP transport 和 session binding。Stream 由 Client registry 管理，关闭 Client 时必须关闭所有已创建的 stream。

## 4. 凭证和认证设计

### 4.1 凭证类型

```text
AccessToken
    value: opaque JWT string
    expires_at: optional integer exp, memory only

RequestSigningKey
    raw key: exactly 32 bytes
    encoding: base58 / hex / base64 / base64url input

WalletSigner
    chain: bsc/evm or solana/svm
    address: wallet address
    sign_login_message(message): signature
```

`StandXCredentials` 应是不可变配置，内部不实现 token 刷新，不打印 token 或私钥。建议提供：

```text
Credentials.from_encoded(access_token, encoded_request_key)
Credentials.request_signer()
Credentials.redacted_repr()
```

### 4.2 钱包登录流程

1. 客户端生成临时 Ed25519 key pair；
2. 由公钥生成 base58 `requestId`；
3. 调用 `prepare-signin?chain=...`；
4. 解析服务端 `signedData` JWT payload；
5. 调用注入的 WalletSigner 对 `payload.message` 签名；
6. 调用 `login` 获取 JWT；
7. 只在内存保存 token 和可选 `exp`；
8. 将 token 同步到 REST 和需要认证的 stream。

钱包私钥的生命周期由调用方管理。SDK 不应要求调用方把钱包私钥交给公共 Client。

### 4.3 请求签名

签名原文严格为：

```text
v1,{request_id},{timestamp_ms},{compact_json_payload}
```

签名 headers：

```text
x-request-sign-version: v1
x-request-id: <request id>
x-request-timestamp: <integer milliseconds>
x-request-signature: <base64 ed25519 signature>
```

要求：

- JSON 使用稳定紧凑序列化；
- decimal 字段必须是 JSON 字符串；
- timestamp 必须是毫秒整数；
- REST 签名时签名 payload 必须与实际发送 body 语义一致；
- Order Response Stream 自动签名时，`x-request-id` 必须与消息 `request_id` 一致；
- 手工 headers 可以覆盖自动生成结果，但应由调用方承担正确性责任。

## 5. REST 功能设计

### 5.1 市场 API

至少设计以下方法：

```text
overview()
symbol_info(symbol)
symbol_market(symbol)
symbol_price(symbol)
depth_book(symbol)
recent_trades(symbol, limit?)
kline_history(symbol, from, to, resolution, countback?)
server_time()
health()
```

市场规则 DTO 必须包含：数量和价格精度、最小/最大数量、最大持仓、最大杠杆、默认杠杆、最大挂单数、价格保护比例、maker/taker 费率、深度档位和启用时间信息。

### 5.2 账户、持仓和成交 API

```text
account.balance()
positions.list(symbol?)
positions.config(symbol)
positions.change_leverage(symbol, leverage)
positions.change_margin_mode(symbol, mode)
trades.list(symbol?, filters...)
trades.funding_history(symbol?, filters...)
trades.funding_rates(symbol, start_time, end_time)
```

余额、价格、数量、费率、PnL、保证金和成交值统一使用 Decimal 或目标语言中等价的精确十进制类型。不能用二进制浮点数做订单精度比较。

### 5.3 订单 API

```text
orders.create(request)
orders.cancel(order_id?, cl_ord_id?)
orders.cancel_many(order_ids?, cl_ord_ids?)
orders.query_order(order_id?, cl_ord_id?)
orders.query_orders(filters...)
orders.query_open_orders(symbol?, limit?)
```

下单请求应支持文档已定义的字段：

- `symbol`；
- `side`: buy/sell；
- `order_type`: limit/market；
- `qty`；
- `price`，限价单必填，市价单禁止；
- `time_in_force`: gtc/ioc/alo；
- `reduce_only`；
- `cl_ord_id`；
- `margin_mode`；
- `leverage`；
- `tp_price` / `sl_price`。

不要为了“通用交易所兼容”自动增加 StandX 文档没有定义的 FOK、stop、post-only 或其他字段。

## 6. 订单规则和状态机

### 6.1 本地校验顺序

1. 校验 symbol 非空；
2. 加载对应 `InstrumentRules`；
3. 所有数量和价格转换为有限 Decimal；
4. 检查 `qty > 0`、最小数量、最大数量；
5. 检查价格精度和数量精度；
6. 检查最大持仓和最大挂单数；
7. 检查杠杆和当前 position config；
8. 检查 `reduce_only` 可用数量；
9. 检查 TP/SL 的正数和精度；
10. 最后才序列化和发送。

默认拒绝，不自动四舍五入。所有本地校验都只是提前发现错误，不能替代服务端最终校验。

### 6.2 reduce-only 设计

`reduce_only` 最大数量不是简单等于当前仓位数量，而是：

```text
available_reduce_qty = position_qty - all_pending_reduce_only_qty
```

pending reduce-only 数量包括 TP/SL 产生的 reduce-only 订单。SDK 必须允许调用方传入当前仓位和 pending reduce-only 汇总，或由更高层的账户状态服务提供；不能凭单个订单事件推算完整仓位。

### 6.3 订单状态

服务端状态必须原样保留，例如：

```text
new / open / filled / canceled / rejected / untriggered
```

本地通信状态另行表达：

```text
submitted
accepted
unknown
restored
```

不要把 `accepted` 当作 `filled`，不要把网络 timeout 当作 rejected，也不要凭 `fill_qty < qty` 虚构服务端不存在的 `partially_filled` 状态。

## 7. WebSocket 设计

### 7.1 两个连接必须分离

```text
Market Stream          -> 市场数据 + 用户 channel
Order Response Stream  -> 异步订单响应
```

不能把订单响应错误地当作普通用户订单 channel，也不能为了复用连接而改变官方消息 envelope。

### 7.2 Market Stream

公开频道：

```text
price
depth_book
public_trade
```

用户频道：

```text
order
position
balance
trade
```

用户频道必须先认证。认证失败时清除本地认证上下文，不得继续发送订阅。订阅只有在 transport 成功发送后才能写入恢复列表。重连时按原顺序恢复，不能默认给深度排序，也不能丢弃顶层 `seq`。

### 7.3 Order Response Stream

消息 envelope 必须保留：

```json
{
  "session_id": "session-1",
  "request_id": "request-1",
  "method": "order:new",
  "header": {},
  "params": "{\"symbol\":\"BTC-USD\"}"
}
```

`params` 是 JSON 字符串，不是嵌套 JSON 对象。pending 关联键是 `session_id + request_id`，不是单独 request ID。禁止复用仍 pending 的 request ID。

订单响应解码：

```text
status=accepted        -> accepted
code=0                 -> success
code>=400              -> rejected
其他                    -> unknown
```

缺少 request ID、session 不匹配、code 不是 JSON 整数、status/message 类型错误时，返回协议错误，并保留 pending，不得因为坏响应误清理请求。

### 7.4 心跳和重连

- 由底层 WebSocket 处理 ping/pong，但 SDK 必须能识别连接断开；
- 连接达到服务端最大生命周期时允许重连；
- 手动关闭后禁止自动重连；
- 连接重试只重建连接和恢复订阅；
- 绝不自动重发 pending 的 `order:new` 或 `order:cancel`；
- 使用指数退避、最大延迟和可注入 jitter；
- 协议错误、非法 URL 和配置错误不应无意义重试。

## 8. REST 与 WebSocket 一致性

### 8.1 REST 是完整快照权威

用户订单流通常只包含部分字段，不能直接用事件覆盖完整订单。推荐流程：

```text
user order event
    -> extract cl_ord_id
    -> query REST order snapshot
    -> compare watermark
    -> update local cache
```

### 8.2 水位线和并发锁

每个 `cl_ord_id` 使用独立 refresh lock：

- 同一订单的事件和恢复查询串行；
- 不同订单可以并行；
- 旧时间戳的快照不能覆盖新快照；
- REST 查询失败不能清除旧快照；
- 查询不到订单不能直接标记为失败；
- 重启后使用 `query_open_orders` 重建可关联缓存；
- 没有 `cl_ord_id` 的订单只能返回调用方，不能进入关联缓存。

### 8.3 未知状态恢复

对任何可能产生副作用的 timeout/disconnect：

1. 保存 `cl_ord_id`、request ID 和操作类型；
2. 标记本地 `unknown`；
3. 不自动重试；
4. 恢复连接或应用重启后按 `cl_ord_id` 查询；
5. 只有 REST 快照或明确的订单响应才能结束未知状态。

## 9. 统一错误模型

跨语言实现应提供稳定错误码，而不是把 HTTP 库异常直接暴露给调用方：

```text
AUTH_FAILED
PERMISSION_DENIED
NOT_FOUND
SERVER_ERROR
TOKEN_EXPIRED
INVALID_SIGNATURE
RATE_LIMITED
REQUEST_TIMEOUT
VALIDATION_ERROR
ORDER_REJECTED
ORDER_UNKNOWN
WS_DISCONNECTED
WS_RESUBSCRIBE_FAILED
PROTOCOL_ERROR
```

错误对象建议包含：

```text
code             SDK 稳定错误码
message          脱敏后的可读信息
request_id       客户端或服务端 request ID
server_code      服务端原始 code，可选
retryable        是否允许调用方考虑重试
retry_after      服务端建议等待时间，可选
transport_error_type   脱敏的传输分类，可选
transport_error_types  脱敏的底层异常类型链，可选
cause            原始异常链，仅供日志关联，不应直接展示
```

错误消息不得包含 JWT、私钥、签名、Authorization、完整请求 body 或完整服务端敏感响应。

HTTP 状态必须按以下规则映射，不能把所有状态折叠为同一个通用错误：

| HTTP/网络情况 | SDK code | retryable | 诊断边界 |
|---|---|---:|---|
| `401` | `AUTH_FAILED` | 否 | JWT 缺失、无效或已失效 |
| `403` | `PERMISSION_DENIED` | 否 | 认证成功但权限不足 |
| `404` | `NOT_FOUND` | 否 | 可能是认证环境、接口版本、域名或凭证类型不匹配；消息应提示调用方检查这些配置 |
| `408` | `REQUEST_TIMEOUT` | 是 | 服务端请求超时 |
| `429` | `RATE_LIMITED` | 是 | 保留合法 `Retry-After` |
| `5xx` | `SERVER_ERROR` | 是 | StandX 服务端异常 |
| DNS/TLS/代理/连接失败 | `PROTOCOL_ERROR`（REST）或 `WS_DISCONNECTED`（WebSocket） | 通常是 | 通过 `transport_error_type` 区分 `DNS error`、`TLS error`、`ProxyError`、`ConnectTimeout`、`ReadTimeout`、`RemoteDisconnect` 等 |

底层异常类型只记录类型名和有限长度的异常链，不记录 URL、Authorization、JWT、私钥、签名或异常原文。调用方应优先依据 `code` 和 `retryable` 决策，再使用 `transport_error_type` 定位 DNS、TLS、代理或远端断开问题。

## 10. 重试和限流

### 10.1 重试矩阵

| 操作 | 默认自动重试 | 原因 |
|---|---:|---|
| 公共 GET 行情 | 可配置 | 无副作用 |
| 账户/订单查询 GET | 可配置 | 只读，但需注意 token 恢复 |
| 认证 prepare/login | 可配置 | 必须保证 nonce/签名生命周期正确 |
| 创建订单 | 否 | 可能重复下单 |
| 单笔/批量撤单 | 否 | 结果未知时重复操作不安全 |
| 改杠杆/保证金 | 否 | 有外部状态副作用 |
| WebSocket 重连 | 是 | 只重连和恢复订阅 |
| WebSocket 订单请求重发 | 否 | 禁止重复交易 |

如果调用方显式确认幂等性，也只能对 `retryable=true` 的错误启用有限重试，并记录重试原因。

### 10.2 Rate limiter

StandX 文档给出 credit-based 限流参数时，实现 token bucket：

```text
cost_per_request = 45
replenish_rate   = 1000 credits/second
capacity         = 900 credits
```

这些参数必须可配置，因为服务端文档可能变化。服务端 429 转换为 `RATE_LIMITED`，保留合法的 `Retry-After`；非法、负数或非有限值必须忽略。限流等待不能无限掩盖调用方错误。

## 11. 设计边界清单

### SDK 应负责

- 协议 endpoint 和 JSON envelope；
- JWT headers；
- Ed25519 请求签名；
- 凭证编码解码；
- Decimal DTO 和订单规则校验；
- REST / WebSocket 连接管理；
- 订阅恢复和 session/request correlation；
- 统一错误；
- 限流和可控重试；
- 订单未知状态和恢复辅助；
- Fake transport 和协议夹具。

### SDK 不应负责

- 交易策略；
- 自动止损策略和投资建议；
- 全局风控和仓位分配；
- 交易机器人调度；
- 私钥生成、托管、备份和持久化；
- 钱包充值、转账、提现和链上交易；
- 自动刷新不存在的 token；
- 自动重发未知订单；
- 凭经验补充官方未定义参数；
- 把服务端状态转换成其他交易所状态体系。

## 12. 测试设计

### 12.1 单元测试

- Decimal 有限性；
- base58/hex/base64 私钥解码；
- 固定 Ed25519 请求签名向量；
- JSON 稳定序列化；
- 订单数量、价格、精度和 reduce-only 校验；
- JWT `exp` 读取；
- 错误映射；
- token bucket 和 retry-after；
- session/request 相关性。

### 12.2 Fake REST

验证：

- endpoint、method、query 参数和 JSON 类型；
- Authorization、x-request-sign-*、x-session-id；
- 余额、持仓、成交、资金费率和订单 DTO；
- 顶层数组与 `{result: [...]}` 两种 envelope；
- 非法 JSON、字段缺失、错误类型和非有限数字；
- timeout 后返回 `ORDER_UNKNOWN`；
- GET 401 可恢复，POST 401 不自动重放。

### 12.3 Fake WebSocket

验证：

- 精确消息 envelope；
- ping/pong、连接关闭和 reconnect backoff；
- 公开/用户 channel；
- 订阅记录只在发送成功后更新；
- 重连按顺序恢复订阅；
- auth 失败清理状态；
- order response 的 session/request 关联；
- 错误响应不误清理 pending；
- pending 订单不自动重发。

### 12.4 集成测试边界

默认不访问真实网络、账户、私钥和交易。需要 PAPER 集成时必须显式启用，并单独标记为 integration test。LIVE 下单不应成为 SDK 默认 CI 的一部分。

## 13. 发布和生产前检查

### 自动化检查

```text
全量单元测试
静态检查
类型检查
构建 wheel/package
diff/secret scan
文档示例检查
```

### 生产前人工检查

1. API Token 已开启 `Trade`，关闭不必要的 `Withdraw`；
2. JWT 和请求签名私钥来自密钥管理系统，不来自提交文件；
3. 使用 PAPER 做行情、查询、连接恢复和最小订单流程验证；
4. LIVE 先进行极小风险灰度，不直接运行大额策略；
5. 监控 `ORDER_UNKNOWN`、`RATE_LIMITED`、WebSocket 断线和恢复失败；
6. 对每个订单保存自己的 `cl_ord_id` 和审计记录；
7. 进程退出前关闭 stream 和 transport；
8. 发现签名密钥泄露时立即撤销 API Token 并轮换密钥。

## 14. 推荐的跨语言接口

```text
Client(config, credentials?, transports?)

MarketService:
  overview
  symbol_info
  symbol_price
  symbol_market
  depth_book
  recent_trades
  kline_history

AccountService:
  balance
  positions
  position_config
  change_leverage
  change_margin_mode
  trades
  funding_history
  funding_rates

OrderService:
  create
  cancel
  cancel_many
  query
  query_many
  open_orders

MarketStream:
  connect
  authenticate
  subscribe
  receive
  reconnect
  close

OrderResponseStream:
  connect
  authenticate
  request
  receive
  decode_response
  recover_pending
  close
```

异步语言使用 Future/Promise/async-await；同步语言也必须保留显式 timeout、close、pending 和未知状态，不应通过阻塞调用隐藏协议生命周期。

## 15. 实施顺序

1. 协议 fixtures、配置和错误模型；
2. 精确数字、凭证解码和 Ed25519 签名向量；
3. HTTP transport 和限流；
4. 市场 REST 和规则 DTO；
5. 账户、持仓、成交、资金费率；
6. 订单请求、校验、查询、撤单和未知状态；
7. WebSocket transport、心跳和重连；
8. Market Stream 和用户频道；
9. Order Response Stream、session/request correlation；
10. REST/Stream 一致性恢复；
11. 文档、Fake Server、CI 和安全扫描；
12. PAPER 集成验证；
13. 由调用方自行决定是否进入 LIVE 灰度。

## 16. 最终验收标准

- 公共 API 不依赖底层 HTTP/WebSocket 类型；
- JWT 查询和 Ed25519 签名交易边界明确；
- base58、hex、base64 凭证不会被错误识别或静默截断；
- 所有金额、价格、数量和费率使用精确十进制；
- 所有订单变更都有明确的未知状态语义；
- timeout、401、429、5xx、断线和坏 envelope 有稳定错误码；
- `x-session-id` 与 Order Response Stream 正确绑定；
- Market Stream 和 Order Response Stream 生命周期分离；
- 订阅可恢复，副作用订单请求不可自动重放；
- REST 快照是订单最终一致性的权威来源；
- Fake REST/WebSocket 可覆盖全部关键协议边界；
- 无真实密钥、JWT、账户和交易进入自动化测试或源码仓库；
- 安装、配置、行情查询、交易签名、恢复和安全限制都有文档示例。
