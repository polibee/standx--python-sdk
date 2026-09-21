from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from ..models.order import CreateOrderRequest
from ..transport.http import HttpTransport


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    code: int
    message: str
    request_id: str


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


class OrdersApi:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def create(self, request: CreateOrderRequest) -> SubmissionResult:
        body: dict[str, object] = {
            "symbol": request.symbol,
            "side": request.side.value,
            "order_type": request.order_type.value,
            "qty": _decimal(request.qty),
            "time_in_force": request.time_in_force.value,
            "reduce_only": request.reduce_only,
        }
        optional = {
            "price": _decimal(request.price),
            "cl_ord_id": request.cl_ord_id,
            "margin_mode": request.margin_mode,
            "leverage": request.leverage,
            "tp_price": _decimal(request.tp_price),
            "sl_price": _decimal(request.sl_price),
        }
        body.update({key: value for key, value in optional.items() if value is not None})
        return self._result(await self._transport.post("/api/new_order", json=body, signed=True))

    async def cancel(
        self, *, order_id: int | None = None, cl_ord_id: str | None = None
    ) -> SubmissionResult:
        if order_id is None and cl_ord_id is None:
            raise ValueError("cancel requires order_id or cl_ord_id")
        body = {
            key: value
            for key, value in {"order_id": order_id, "cl_ord_id": cl_ord_id}.items()
            if value is not None
        }
        return self._result(await self._transport.post("/api/cancel_order", json=body, signed=True))

    async def cancel_many(
        self, *, order_ids: list[int] | None = None, cl_ord_ids: list[str] | None = None
    ) -> SubmissionResult:
        if not order_ids and not cl_ord_ids:
            raise ValueError("cancel_many requires order_ids or cl_ord_ids")
        body: dict[str, object] = {}
        if order_ids:
            body["order_id_list"] = order_ids
        if cl_ord_ids:
            body["cl_ord_id_list"] = cl_ord_ids
        return self._result(
            await self._transport.post("/api/cancel_orders", json=body, signed=True)
        )

    @staticmethod
    def _result(value: dict[str, object]) -> SubmissionResult:
        typed = cast(dict[str, Any], value)
        return SubmissionResult(int(typed["code"]), str(typed["message"]), str(typed["request_id"]))


__all__ = ["OrdersApi", "SubmissionResult"]
