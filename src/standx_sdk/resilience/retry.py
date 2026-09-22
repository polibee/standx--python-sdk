"""Explicit asynchronous retry policy for safe, replayable operations."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import TypeVar

from ..errors import ErrorCode, StandXError

_T = TypeVar("_T")


class RetryPolicy:
    """Retry only explicitly wrapped operations that fail with retryable SDK errors."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        initial_delay: float = 0.25,
        max_delay: float = 5.0,
        jitter: Callable[[float], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retryable_codes: frozenset[ErrorCode] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not math.isfinite(initial_delay) or initial_delay < 0:
            raise ValueError("initial_delay must be finite and non-negative")
        if not math.isfinite(max_delay) or max_delay <= 0:
            raise ValueError("max_delay must be finite and positive")
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self._jitter = jitter
        self._sleep = sleep
        self._retryable_codes = retryable_codes

    async def execute(self, operation: Callable[[], Awaitable[_T]]) -> _T:
        delay = self.initial_delay
        for attempt in range(self.max_attempts):
            try:
                return await operation()
            except StandXError as error:
                if not self._can_retry(error) or attempt == self.max_attempts - 1:
                    raise
                wait = error.retry_after_seconds
                if wait is None:
                    wait = delay
                wait = min(wait, self.max_delay)
                if self._jitter is not None:
                    wait = self._jitter(wait)
                if not math.isfinite(wait) or wait < 0:
                    raise ValueError("jitter must return a finite non-negative delay")
                await self._sleep(wait)
                delay = min(delay * 2, self.max_delay)
        raise AssertionError("retry loop did not return")

    def _can_retry(self, error: StandXError) -> bool:
        if not error.retryable:
            return False
        return self._retryable_codes is None or error.code in self._retryable_codes
