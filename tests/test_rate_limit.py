import asyncio

from standx_sdk.resilience.rate_limit import CreditRateLimiter


def test_credit_limiter_enforces_documented_burst_and_replenishment() -> None:
    now = [0.0]
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    limiter = CreditRateLimiter(clock=lambda: now[0], sleep=sleep)

    async def consume_burst() -> None:
        for _ in range(20):
            await limiter.acquire()
        await limiter.acquire()

    asyncio.run(consume_burst())

    assert limiter.available_credits == 0
    assert sleeps == [0.045]


def test_credit_limiter_rejects_invalid_configuration() -> None:
    try:
        CreditRateLimiter(capacity=0)
    except ValueError as error:
        assert "capacity" in str(error)
    else:
        raise AssertionError("capacity must be positive")
