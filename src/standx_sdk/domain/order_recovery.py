"""Consistency helpers for recovering orders across stream and REST sources."""

import asyncio
from collections.abc import Awaitable, Callable

from ..models.order import Order
from ..models.stream import UserOrderEvent
from ..streams.order_response import OrderResponseStream


class OrderStateReconciler:
    """Keep REST order snapshots as the authority after stream notifications."""

    def __init__(self, query_order: Callable[[str], Awaitable[Order | None]]) -> None:
        self._query_order = query_order
        self._orders: dict[str, Order] = {}
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    def get(self, cl_ord_id: str | None) -> Order | None:
        if cl_ord_id is None:
            return None
        return self._orders.get(cl_ord_id)

    async def apply_user_event(self, event: UserOrderEvent) -> Order | None:
        """Re-read REST after a user event instead of merging partial event fields."""

        if event.cl_ord_id is None:
            return None
        lock = self._refresh_locks.setdefault(event.cl_ord_id, asyncio.Lock())
        async with lock:
            order = await self._query_order(event.cl_ord_id)
            if order is not None:
                self._orders[event.cl_ord_id] = order
        return order

    async def recover_pending(self, stream: OrderResponseStream) -> list[Order]:
        """Recover only pending requests whose client ID has a REST snapshot."""

        async def query_locked(cl_ord_id: str) -> Order | None:
            lock = self._refresh_locks.setdefault(cl_ord_id, asyncio.Lock())
            async with lock:
                order = await self._query_order(cl_ord_id)
                if order is not None:
                    self._orders[cl_ord_id] = order
                return order

        recovered = await stream.recover_pending(query_locked)
        typed: list[Order] = []
        for value in recovered:
            if isinstance(value, Order) and value.cl_ord_id is not None:
                typed.append(value)
        return typed

    async def restore_open_orders(
        self, query_open_orders: Callable[[], Awaitable[list[Order]]]
    ) -> list[Order]:
        """Rebuild the cache from REST after process restart."""

        restored = await query_open_orders()
        self._orders = {
            order.cl_ord_id: order for order in restored if order.cl_ord_id is not None
        }
        return restored


__all__ = ["OrderStateReconciler"]
