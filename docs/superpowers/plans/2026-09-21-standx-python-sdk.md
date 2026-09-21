# StandX Python SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested Python SDK for the StandX Perps API using only the endpoints, fields, enums, and WebSocket protocols documented in `docs/standx.md`.

**Architecture:** A typed public client composes independent authentication, signing, REST, WebSocket, models, error, retry, rate-limit, and testing modules. REST and the two StandX WebSocket endpoints remain separate; raw JSON is converted to DTOs and all decimal values are serialized as JSON strings.

**Tech Stack:** Python 3.11+, `httpx`, `websockets`, `pydantic`, `cryptography`/`PyNaCl` as needed for Ed25519, `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy`, and `build`.

**Spec:** `docs/standx-sdk-design.md`

## Global Constraints

- The SDK supports only StandX Perps Python APIs; no Go SDK and no trading-bot adapter.
- Authentication uses the documented `api.standx.com/v1/offchain` flow; trading REST uses `https://perps.standx.com`.
- Decimal request values such as `qty` and `price` are serialized as JSON strings; integer values such as timestamps remain JSON integers.
- StandX order types are only `limit` and `market`; time-in-force values are only `gtc`, `ioc`, and `alo`.
- `cl_ord_id` is optional in the protocol; the SDK generates one by default and preserves the server value.
- `reduce_only`, `margin_mode`, `leverage`, `tp_price`, and `sl_price` use the exact documented request fields.
- Market rules come from `GET /api/query_symbol_info`; no undocumented `minimum_notional`, `FOK`, stop-order, position-side, or independent `post_only` feature may be added.
- Market Stream and Order Response Stream are two separate WebSocket endpoints; user channels are subscriptions within Market Stream.
- No real private key, account, order, or trade is used in automated tests.
- PAPER/test behavior is the default; LIVE access is not claimed or validated by this implementation.

## Review Focus

- Decimal inputs supplied as Python floats must be rejected or converted only through explicit string/Decimal construction; tests pin JSON string serialization.
- `new_order` and `cancel_order` HTTP success must remain “accepted/submitted,” not final execution/cancellation; tests require Order Response Stream correlation.
- `reduce_only` quantity must subtract all pending reduce-only orders, including TP/SL orders, before local acceptance.
- `alo` rejection must be represented as an asynchronous order rejection, not as a successful fill.
- WebSocket disconnects after 24 hours or missing Pong must restore subscriptions without losing request/session correlation.

---

### Task 1: Package and verification baseline

**Files:**
- Create: `pyproject.toml`
- Create: `src/standx_sdk/__init__.py`
- Create: `src/standx_sdk/config.py`
- Create: `tests/test_package_baseline.py`
- Create: `README.md`
- Create: `.gitignore`

**Interfaces:**
- Produces `Environment`, `ClientConfig`, and an importable `standx_sdk` package.

- [ ] **Step 1: Write the failing import and configuration tests**

```python
from standx_sdk import ClientConfig, Environment


def test_paper_is_the_default_environment():
    config = ClientConfig(base_url="https://perps.standx.com")
    assert config.environment is Environment.PAPER
```

- [ ] **Step 2: Run the baseline test and verify it fails**

Run: `python -m pytest tests/test_package_baseline.py -q`

Expected: FAIL because the package and configuration do not exist.

- [ ] **Step 3: Add package metadata and minimal configuration**

Implement `ClientConfig` with validated `base_url`, PAPER default, request timeout, and explicit LIVE opt-in. Configure src layout, pytest, ruff, mypy, and build in `pyproject.toml`.

- [ ] **Step 4: Run baseline checks**

Run: `python -m pytest tests/test_package_baseline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```text
chore: scaffold standx python sdk package
```

### Task 2: Protocol models and unified errors

**Files:**
- Create: `src/standx_sdk/models/common.py`
- Create: `src/standx_sdk/models/market.py`
- Create: `src/standx_sdk/models/order.py`
- Create: `src/standx_sdk/models/account.py`
- Create: `src/standx_sdk/models/position.py`
- Create: `src/standx_sdk/errors/codes.py`
- Create: `src/standx_sdk/errors/exceptions.py`
- Create: `tests/test_models.py`
- Create: `tests/test_errors.py`

**Interfaces:**
- Produces `OrderType`, `OrderSide`, `TimeInForce`, `MarginMode`, `OrderStatus`, `CreateOrderRequest`, `Order`, `InstrumentRules`, `Trade`, and `StandXError`.

- [ ] **Step 1: Write model tests for exact StandX enums and decimal fields**

```python
def test_standx_order_enums_are_exact():
    assert OrderType.LIMIT.value == "limit"
    assert TimeInForce.ALO.value == "alo"
    assert OrderStatus.UNTRIGGERED.value == "untriggered"
```

- [ ] **Step 2: Add DTOs using Decimal for documented decimal fields**

Model `query_symbol_info`, order, position, balance, trade, and price responses. Preserve documented raw status strings where the local examples conflict (`open` versus `new`). Do not add undocumented order fields.

- [ ] **Step 3: Add validation tests**

Test market orders without price, limit orders without price, invalid enum values, invalid non-positive quantities, and decimal parsing.

- [ ] **Step 4: Implement error mapping types**

Add HTTP status mapping for 400/401/403/404/429/500 and SDK-local codes for timeout, protocol, and unknown asynchronous result.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/test_models.py tests/test_errors.py -q`

Expected: PASS.

Commit message: `feat: add standx protocol models and errors`

### Task 3: Authentication and request signing

**Files:**
- Create: `src/standx_sdk/auth/service.py`
- Create: `src/standx_sdk/auth/models.py`
- Create: `src/standx_sdk/auth/signers.py`
- Create: `src/standx_sdk/signing/request.py`
- Create: `src/standx_sdk/signing/jwt.py`
- Create: `tests/vectors/signing.json`
- Create: `tests/test_signing.py`
- Create: `tests/test_auth.py`

**Interfaces:**
- Produces `WalletSigner`, `RequestSigner`, `prepare_signin`, `login`, token state, and `sign_request`.

- [ ] **Step 1: Add fixed request-signature vectors**

Pin the exact message format:

```text
v1,{request_id},{timestamp},{payload}
```

Assert the Base64 Ed25519 signature for a fixed key, request ID, timestamp, and JSON payload.

- [ ] **Step 2: Implement injectable wallet signers**

Keep EVM/Solana wallet message signing behind protocols. Do not accept a raw private key in the client or persist any key material.

- [ ] **Step 3: Implement `prepare-signin` and `login` with a fake transport**

Use the local auth paths and preserve the documented `signedData`, `token`, `address`, `alias`, `chain`, and `perpsAlpha` fields.

- [ ] **Step 4: Test token expiry and sensitive-data redaction**

Assert expired tokens are rejected and exception/log payloads never contain a token or signature.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/test_signing.py tests/test_auth.py -q`

Expected: PASS.

Commit message: `feat: add standx authentication and request signing`

### Task 4: REST transport and documented REST APIs

**Files:**
- Create: `src/standx_sdk/rest/transport.py`
- Create: `src/standx_sdk/rest/markets.py`
- Create: `src/standx_sdk/rest/account.py`
- Create: `src/standx_sdk/rest/orders.py`
- Create: `src/standx_sdk/rest/positions.py`
- Create: `src/standx_sdk/rest/trades.py`
- Create: `src/standx_sdk/retry/policy.py`
- Create: `src/standx_sdk/rate_limit/limiter.py`
- Create: `tests/test_rest_markets.py`
- Create: `tests/test_rest_orders.py`
- Create: `tests/test_rest_account.py`

**Interfaces:**
- Produces typed methods for `/api/new_order`, `/api/cancel_order`, `/api/cancel_orders`, `/api/query_order`, `/api/query_orders`, `/api/query_open_orders`, `/api/change_leverage`, `/api/change_margin_mode`, `/api/query_position_config`, `/api/query_positions`, `/api/query_balance`, `/api/query_symbol_info`, `/api/query_trades`, `/api/query_funding_rates`, and documented public market endpoints.

- [ ] **Step 1: Write fake-transport tests for exact paths, methods, and JSON types**

Assert `qty`, `price`, leverage, IDs, query parameters, and `x-session-id` match `docs/standx.md` exactly.

- [ ] **Step 2: Implement common transport**

Add Bearer auth, request signatures for signed bodies, integer millisecond timestamps, decimal-string serialization, timeout mapping, and HTTP error mapping.

- [ ] **Step 3: Implement market and account APIs**

Map symbol info, market overview, symbol price, depth book, recent trades, funding, balance, position, and position config into DTOs. Preserve nullable fields.

- [ ] **Step 4: Implement order APIs and async semantics**

Send the exact documented fields; allow server-generated `cl_ord_id`; require at least one of `order_id`/`cl_ord_id` for single cancellation/query and at least one list for bulk cancellation.

- [ ] **Step 5: Implement rate limits and safe retry policy**

Represent the documented 45-credit request cost, 1,000-credit/sec replenish rate, 900-credit burst, and 429 response without assuming these values can never change. Never retry order creation automatically by default.

- [ ] **Step 6: Run REST tests and commit**

Run: `python -m pytest tests/test_rest_markets.py tests/test_rest_orders.py tests/test_rest_account.py -q`

Expected: PASS with no external network.

Commit message: `feat: add standx rest api client`

### Task 5: Market Stream and Order Response Stream

**Files:**
- Create: `src/standx_sdk/websocket/connection.py`
- Create: `src/standx_sdk/websocket/market_stream.py`
- Create: `src/standx_sdk/websocket/order_response_stream.py`
- Create: `src/standx_sdk/testing/fake_websocket.py`
- Create: `tests/test_market_stream.py`
- Create: `tests/test_order_response_stream.py`

**Interfaces:**
- Produces a Market Stream client for `price`, `depth_book`, `public_trade`, `order`, `position`, `balance`, and `trade`; produces an Order Response Stream client for `auth:login`, `order:new`, and `order:cancel`.

- [ ] **Step 1: Write fake WebSocket tests for message envelopes**

Assert Market Stream subscription envelopes and Order Response Stream `session_id`, `request_id`, `method`, `header`, and stringified `params`.

- [ ] **Step 2: Implement Ping/Pong, reconnect, and lifecycle limits**

Handle server Ping, missing Pong disconnect, manual close, backoff, subscription replay, and 24-hour server termination.

- [ ] **Step 3: Implement Market Stream channel parsing**

Parse public and authenticated channel DTOs; preserve `seq`; do not sort depth levels implicitly.

- [ ] **Step 4: Implement Order Response correlation**

Correlate by stable `session_id` and per-request `request_id`; distinguish accepted, success, and rejection responses; return local unknown state after disconnect.

- [ ] **Step 5: Run WebSocket tests and commit**

Run: `python -m pytest tests/test_market_stream.py tests/test_order_response_stream.py -q`

Expected: PASS with the fake server only.

Commit message: `feat: add standx websocket streams`

### Task 6: Client composition, documentation, and release checks

**Files:**
- Create: `src/standx_sdk/client.py`
- Modify: `src/standx_sdk/__init__.py`
- Modify: `README.md`
- Create: `CHANGELOG.md`
- Create: `tests/test_client.py`
- Create: `tests/test_security_boundaries.py`

**Interfaces:**
- Produces the public `StandXClient` with `auth`, `markets`, `account`, `positions`, `orders`, `trades`, `market_stream`, and `order_response_stream` services.

- [ ] **Step 1: Test client composition**

Assert all services share configuration and transport dependencies without exposing raw HTTP responses.

- [ ] **Step 2: Add PAPER/LIVE safety tests**

Assert PAPER is default, LIVE requires explicit configuration, and no test accesses a real endpoint or real credential.

- [ ] **Step 3: Write README examples from documented fields**

Include authentication, market query, symbol rules, order creation, async order confirmation, cancellation, and WebSocket subscription examples.

- [ ] **Step 4: Run complete verification**

Run:

```text
python -m pytest -q
ruff check .
mypy src
python -m build
```

Expected: all commands pass without external network access.

- [ ] **Step 5: Commit release preparation**

Commit message: `release: prepare standx python sdk`

### Task 7: Git initialization and GitHub push gate

**Files:**
- Modify: `.gitignore`, `README.md`, `CHANGELOG.md` if release checks require it.

- [ ] **Step 1: Inspect and confirm remote target**

Run `git status`, `git remote -v`, and `gh auth status`. Do not invent or overwrite a remote URL.

- [ ] **Step 2: Scan for secrets and generated artifacts**

Verify no private key, JWT, `.env`, build cache, or local credentials is tracked.

- [ ] **Step 3: Initialize Git and create the planned commits**

Only after verification, initialize the repository if needed and preserve the stage-level commit boundaries above.

- [ ] **Step 4: Push only after the user confirms the GitHub destination**

Run the exact confirmed remote push and verify the branch and tag on GitHub.

## Self-Review Checklist

- [x] Every documented order enum is represented; undocumented FOK/stop/post-only fields are excluded.
- [x] `query_symbol_info` owns quantity/price/position constraints.
- [x] `cl_ord_id` matches the documented optional behavior.
- [x] The two documented WebSocket endpoints are separated correctly.
- [x] REST success versus asynchronous execution/cancellation is tested separately.
- [x] Local tests avoid real network, credentials, and trades.
- [x] GitHub push is gated on a confirmed remote target and secret scan.
