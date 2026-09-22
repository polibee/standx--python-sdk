# Changelog

All notable changes to this project are documented here.

## 0.1.0 - 2026-09-21

### Added

- Typed Python client for the documented StandX Perps REST API.
- Wallet authentication boundary and Ed25519 request signing.
- Typed market, account, position, trade, funding, order, and instrument-rule DTOs.
- Local order validation for quantity, price precision, leverage, position limits, and reduce-only rules.
- Market Stream and Order Response Stream with authentication, reconnect backoff, heartbeat configuration,
  subscription recovery, session/request correlation, and offline Fake WebSocket testing.
- REST-backed order state reconciliation for user events, pending response recovery, and process restart recovery.
- Stable error codes, timeout/unknown-order handling, rate limiting, and server error context.
- Automatic `cl_ord_id` generation for orders that omit a client order ID, with the ID retained in `SubmissionResult`.
- Explicit validation of order `margin_mode` values and optional matching against current leverage/margin configuration.
- Positive and price-precision validation for `tp_price` and `sl_price`.
- Typed `RecentTrade` snapshots preserving documented `is_buyer_taker` and `quote_qty` fields.
- Typed `FundingRate` snapshots for documented funding-rate history fields.
- Added documented pagination, time-range, and side filters for user trades and funding history.
- Expanded `PositionSnapshot` with documented margin, liquidation, mark-price, and position-value fields.
- Expanded `Order` snapshots with documented lock, margin, position, source, block, and timestamp fields.
- Expanded symbol market DTOs with documented base, quote, and spread fields.
- Added injectable authentication headers to Order Response Stream requests.
- Validated Order Response authentication header correlation and non-empty values.
- Serialized concurrent REST refreshes for the same client order ID while keeping different orders independent.
- Applied the same refresh lock to pending order-response recovery and user order events.
- Preserved Market Stream authentication streams across reconnects and cleared stale auth state after reconnect failures.
- Rejected non-finite numeric values in REST and Market Stream DTO decoding as protocol errors.
- Enforced locally tracked JWT expiry before authenticated REST requests with a stable `TOKEN_EXPIRED` error.
- Added explicit `RetryPolicy` backoff with `retry-after` support; REST retries remain opt-in.
- Hardened WebSocket connection backoff to avoid retrying configuration and protocol errors.
- Added order reconciliation watermarks to prevent stale user events or REST snapshots overwriting newer state.
- Serialized open-order restoration with per-order locks and freshness checks.
- Hardened configuration and transport boundaries against non-finite timeouts and empty WebSocket endpoints.
- Mapped single and bulk cancel timeouts to non-retryable `ORDER_UNKNOWN` to prevent duplicate cancellation requests.
- Wired `StandXClient` order creation to fetch and cache symbol rules before local validation when rules are omitted.
- Added a typed Order Response Stream `authenticate()` helper for documented `auth:login` requests.
- Preserved Market Stream top-level `seq` values in all typed channel events.
- Normalized malformed Order Response status codes to the stable protocol error.
- Normalized Market Stream authentication rejection and malformed responses to stable SDK errors.
- Normalized malformed Market Stream DTO payloads to the stable protocol error while preserving unknown-channel validation.
- Completed README examples for login, typed REST queries, asynchronous order responses, cancellation, and user streams.
- Enforced session correlation in direct Order Response resolution without clearing mismatched pending requests.
- Enforced strict JSON-integer validation for Market Stream authentication and Order Response codes.
- Recorded Market Stream subscriptions only after successful transport sends.
- Normalized WebSocket receive disconnects to retryable `WS_DISCONNECTED` errors.
- Normalized WebSocket send disconnects for subscriptions, authentication, and order requests.
- Prevented closed streams from entering reconnect backoff loops.
- Normalized malformed typed market REST responses to non-retryable `PROTOCOL_ERROR` errors.
- Normalized malformed typed account, position, trade, and funding REST responses to non-retryable
  `PROTOCOL_ERROR` errors.
- Normalized malformed typed order query, submission, cancellation, and bulk-cancellation responses
  to non-retryable `PROTOCOL_ERROR` errors.
- Added async context-manager lifecycle for `StandXClient`; closing is idempotent and closed clients
  reject new stream creation.
- Made `HttpTransport.aclose()` idempotent and normalized requests after transport closure to
  non-retryable `PROTOCOL_ERROR`.
- Normalized malformed signedData JWT payloads and login authentication fields to non-retryable
  `PROTOCOL_ERROR` errors.
- Hardened Order Response request correlation: empty/duplicate pending IDs are rejected, and
  malformed responses cannot clear pending requests.
- Normalized non-object Market Stream and Order Response envelopes to `PROTOCOL_ERROR`.
- Made malformed or negative `Retry-After` headers harmless while preserving `RATE_LIMITED` errors.
- Rejected non-finite rate-limiter configuration and request costs to prevent invalid waits.
- Rejected non-finite WebSocket ping interval and timeout values.
- Rejected non-finite order quantity, price, TP, and SL Decimal values before serialization.
- Added successful `symbol_info` rule caching with explicit per-symbol refresh and cache clearing.
- Serialized concurrent first-load requests per symbol so one in-flight REST fetch populates the cache.
- Added in-memory JWT `exp` tracking and `AuthService.is_token_expired()` without persisting tokens.
- Added protocol-error validation for non-integer Market Stream sequence values.
- Restricted public account and market query methods to typed DTO responses; raw transport payloads are internal only.
- Added typed `client.positions` and `client.trades` service views backed by the shared account transport.
- Added direct `market_stream()` and `order_response_stream()` client factories.
- Enforced required authentication headers for Order Response order requests.
- Expanded `InstrumentRules` with documented enabled and lifecycle timestamp metadata.
- Expanded Market Stream user order events with documented order snapshot fields.
- Expanded Market Stream position and balance events with documented account metadata.
- Expanded Market Stream price events with documented base, quote, and timestamp fields.

### Safety

- Defaults to `PAPER`.
- Automated tests do not access real accounts, private keys, or external trading endpoints.
- Order creation and cancellation are not automatically retried after submission or timeout.
- An order request timeout is reported as `ORDER_UNKNOWN`; callers must query by `cl_ord_id` before retrying.
