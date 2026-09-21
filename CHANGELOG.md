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

### Safety

- Defaults to `PAPER`.
- Automated tests do not access real accounts, private keys, or external trading endpoints.
- Order creation and cancellation are not automatically retried after submission or timeout.
- An order request timeout is reported as `ORDER_UNKNOWN`; callers must query by `cl_ord_id` before retrying.
