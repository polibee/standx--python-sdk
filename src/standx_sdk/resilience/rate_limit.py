"""StandX credit-based token bucket limiter."""

import asyncio
import time
from collections.abc import Awaitable, Callable


class CreditRateLimiter:
    """Limit requests using StandX's documented 45/1000/900 credit budget."""

    def __init__(
        self,
        *,
        cost_per_request: float = 45.0,
        replenish_rate: float = 1000.0,
        capacity: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if cost_per_request <= 0:
            raise ValueError("cost_per_request must be positive")
        if replenish_rate <= 0:
            raise ValueError("replenish_rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if cost_per_request > capacity:
            raise ValueError("cost_per_request must not exceed capacity")
        self.cost_per_request = cost_per_request
        self.replenish_rate = replenish_rate
        self.capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._credits = capacity
        self._last_update = clock()

    @property
    def available_credits(self) -> float:
        self._refill()
        return self._credits

    async def acquire(self, cost: float | None = None) -> None:
        requested = self.cost_per_request if cost is None else cost
        if requested <= 0 or requested > self.capacity:
            raise ValueError("cost must be positive and no greater than capacity")
        while True:
            self._refill()
            if self._credits >= requested:
                self._credits -= requested
                return
            wait_seconds = (requested - self._credits) / self.replenish_rate
            await self._sleep(wait_seconds)

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_update)
        self._credits = min(self.capacity, self._credits + elapsed * self.replenish_rate)
        self._last_update = now
