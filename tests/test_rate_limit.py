import asyncio
import math

from standx_sdk.errors import ErrorCode, StandXError
from standx_sdk.resilience.rate_limit import CreditRateLimiter
from standx_sdk.resilience.retry import RetryPolicy


def test_retry_policy_uses_retry_after_then_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            error = StandXError(ErrorCode.RATE_LIMITED, "slow", retryable=True)
            error.retry_after_seconds = 2.0
            raise error
        return "ok"

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    result = asyncio.run(
        RetryPolicy(initial_delay=0.1, max_delay=1.0, sleep=sleep).execute(operation)
    )

    assert result == "ok"
    assert attempts == 2
    assert sleeps == [1.0]


def test_retry_policy_does_not_retry_non_retryable_errors() -> None:
    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise StandXError(ErrorCode.VALIDATION_ERROR, "invalid")

    try:
        asyncio.run(RetryPolicy(sleep=lambda delay: asyncio.sleep(0)).execute(operation))
    except StandXError as error:
        assert error.code is ErrorCode.VALIDATION_ERROR
    else:
        raise AssertionError("non-retryable errors must be raised")
    assert attempts == 1


def test_retry_policy_uses_exponential_backoff_and_rejects_bad_jitter() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise StandXError(ErrorCode.REQUEST_TIMEOUT, "timeout", retryable=True)

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    try:
        asyncio.run(
            RetryPolicy(max_attempts=3, initial_delay=0.25, max_delay=2, sleep=sleep).execute(
                operation
            )
        )
    except StandXError:
        pass
    else:
        raise AssertionError("retry policy must raise after max attempts")
    assert attempts == 3
    assert sleeps == [0.25, 0.5]

    async def no_sleep(delay: float) -> None:
        return None

    try:
        asyncio.run(
            RetryPolicy(jitter=lambda delay: float("nan"), sleep=no_sleep).execute(operation)
        )
    except ValueError as error:
        assert "finite" in str(error)
    else:
        raise AssertionError("non-finite jitter must fail")


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
