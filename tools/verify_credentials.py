"""Run read-only StandX credential and protocol checks from the local .env file."""

import asyncio
import os
from pathlib import Path

from standx_sdk import ClientConfig, Environment, StandXClient, StandXCredentials
from standx_sdk.errors import StandXError


def _load_local_env(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"missing credential file: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is empty in .env")
    return value


async def _verify() -> None:
    jwt = _required("STANDX_JWT")
    environment = Environment(_required("STANDX_ENVIRONMENT").lower())
    symbol = _required("STANDX_SYMBOL")
    config = ClientConfig(
        base_url=_required("STANDX_BASE_URL"),
        auth_base_url=_required("STANDX_AUTH_BASE_URL"),
        environment=environment,
    )

    encoded_key = os.environ.get("STANDX_ED25519_PRIVATE_KEY", "").strip()
    if not encoded_key:
        encoded_key = _required("STANDX_ED25519_PRIVATE_KEY_HEX")
    try:
        request_signing_key = StandXCredentials.decode_request_signing_key(encoded_key)
    except ValueError as exc:
        client = StandXClient(config, access_token=jwt)
        try:
            await _run_readonly_checks(client, environment, symbol, "JWT")
        finally:
            await client.close_async()
        raise SystemExit(f"JWT passed; request signing key invalid: {exc}") from exc

    credentials = StandXCredentials(
        access_token=jwt,
        request_signing_key=request_signing_key,
    )
    client = StandXClient(config, credentials=credentials)
    try:
        await _run_readonly_checks(client, environment, symbol, "JWT + Ed25519")
    except StandXError as exc:
        print(f"credential verification: failed ({exc.code.value})")
        print(f"message: {exc.message}")
        if exc.server_code is not None:
            print(f"server_code: {exc.server_code}")
        raise SystemExit(1) from exc
    finally:
        await client.close_async()


async def _run_readonly_checks(
    client: StandXClient, environment: Environment, symbol: str, auth_label: str
) -> None:
    try:
        overview = await client.markets.overview()
        rules = await client.markets.symbol_info(symbol)
        balance = await client.account.balance()
        positions = await client.positions.list(symbol=symbol)
        print(f"{auth_label} read-only verification: passed")
        print(f"environment: {environment.value}")
        print(f"market symbols: {len(overview.symbols)}")
        print(f"verified symbol: {rules.symbol}")
        print(f"account balance: {balance.balance}")
        print(f"positions for {symbol}: {len(positions)}")
        print("mutations: none (read-only verification)")
    except StandXError as exc:
        print(f"credential verification: failed ({exc.code.value})")
        print(f"message: {exc.message}")
        if exc.server_code is not None:
            print(f"server_code: {exc.server_code}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    _load_local_env(Path(__file__).resolve().parents[1] / ".env")
    asyncio.run(_verify())
