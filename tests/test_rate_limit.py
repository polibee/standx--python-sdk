import asyncio
import math

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


def test_credit_limiter_rejects_non_finite_configuration_and_cost() -> None:
    for kwargs in (
        {"cost_per_request": math.nan},
        {"replenish_rate": math.inf},
        {"capacity": math.nan},
    ):
        try:
            CreditRateLimiter(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("non-finite limiter configuration must fail")

    limiter = CreditRateLimiter()

    async def acquire_non_finite_cost() -> None:
        await limiter.acquire(math.nan)

    try:
        asyncio.run(acquire_non_finite_cost())
    except ValueError as error:
        assert "cost" in str(error)
    else:
        raise AssertionError("non-finite request cost must fail")
