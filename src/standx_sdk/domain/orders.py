import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from ..errors import ErrorCode, StandXError
from ..models.market import InstrumentRules
from ..models.order import CreateOrderRequest, MarginMode, Order
from ..transport.http import HttpTransport
from ..validation.orders import validate_order


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    code: int
    message: str
    request_id: str
    cl_ord_id: str | None = None


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


class OrdersApi:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def create(
        self,
        request: CreateOrderRequest,
        *,
        rules: InstrumentRules | None = None,
        position_qty: Decimal | None = None,
        pending_reduce_only_qty: Decimal = Decimal(0),
        position_leverage: int | None = None,
        position_margin_mode: str | None = None,
    ) -> SubmissionResult:
        if rules is not None:
            validate_order(
                request,
                rules,
                position_qty=position_qty,
                pending_reduce_only_qty=pending_reduce_only_qty,
                position_leverage=position_leverage,
                position_margin_mode=position_margin_mode,
            )
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
            "cl_ord_id": request.cl_ord_id or str(uuid.uuid4()),
            "margin_mode": (
                request.margin_mode.value
                if isinstance(request.margin_mode, MarginMode)
                else request.margin_mode
            ),
            "leverage": request.leverage,
            "tp_price": _decimal(request.tp_price),
            "sl_price": _decimal(request.sl_price),
        }
        body.update({key: value for key, value in optional.items() if value is not None})
        try:
            response = await self._transport.post("/api/new_order", json=body, signed=True)
        except StandXError as exc:
            if exc.code is not ErrorCode.REQUEST_TIMEOUT:
                raise
            raise StandXError(
                ErrorCode.ORDER_UNKNOWN,
                "new order request timed out; query the order by cl_ord_id before retrying",
                request_id=exc.request_id,
                retryable=False,
                server_code=exc.server_code,
            ) from exc
        return self._result(response, fallback_cl_ord_id=str(body["cl_ord_id"]))

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

    async def query_order(
        self, *, order_id: int | None = None, cl_ord_id: str | None = None
    ) -> Order:
        if order_id is None and cl_ord_id is None:
            raise ValueError("query_order requires order_id or cl_ord_id")
        params = {
            key: value
            for key, value in {"order_id": order_id, "cl_ord_id": cl_ord_id}.items()
            if value is not None
        }
        return _order_from(await self._transport.get("/api/query_order", params=params))

    async def query_orders(
        self,
        *,
        symbol: str | None = None,
        status: str | None = None,
        order_type: str | None = None,
        start: str | None = None,
        end: str | None = None,
        last_id: int | None = None,
        limit: int | None = None,
    ) -> list[Order]:
        params = _query_params(
            symbol=symbol,
            status=status,
            order_type=order_type,
            start=start,
            end=end,
            last_id=last_id,
            limit=limit,
        )
        response = cast(dict[str, Any], await self._transport.get("/api/query_orders", params=params))
        return [_order_from(item) for item in response.get("result", [])]

    async def query_open_orders(
        self, *, symbol: str | None = None, limit: int | None = None
    ) -> list[Order]:
        params = _query_params(symbol=symbol, limit=limit)
        response = cast(
            dict[str, Any], await self._transport.get("/api/query_open_orders", params=params)
        )
        return [_order_from(item) for item in response.get("result", [])]

    @staticmethod
    def _result(
        value: dict[str, object], *, fallback_cl_ord_id: str | None = None
    ) -> SubmissionResult:
        typed = cast(dict[str, Any], value)
        cl_ord_id = typed.get("cl_ord_id")
        return SubmissionResult(
            int(typed["code"]),
            str(typed["message"]),
            str(typed["request_id"]),
            cl_ord_id if isinstance(cl_ord_id, str) else fallback_cl_ord_id,
        )


__all__ = ["OrdersApi", "SubmissionResult"]


def _query_params(**values: object) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def _order_from(value: object) -> Order:
    typed = cast(dict[str, Any], value)
    return Order(
        id=int(typed["id"]),
        cl_ord_id=typed.get("cl_ord_id"),
        symbol=str(typed["symbol"]),
        side=str(typed["side"]),
        order_type=str(typed["order_type"]),
        qty=Decimal(str(typed["qty"])),
        fill_qty=Decimal(str(typed["fill_qty"])),
        fill_avg_price=Decimal(str(typed["fill_avg_price"])),
        status=str(typed["status"]),
        time_in_force=str(typed["time_in_force"]),
        reduce_only=bool(typed["reduce_only"]),
        price=None if typed.get("price") is None else Decimal(str(typed["price"])),
        leverage=None if typed.get("leverage") is None else int(typed["leverage"]),
        margin_mode=typed.get("margin_mode"),
        avail_locked=(
            None if typed.get("avail_locked") is None else Decimal(str(typed["avail_locked"]))
        ),
        closed_block=None if typed.get("closed_block") is None else int(typed["closed_block"]),
        created_at=typed.get("created_at"),
        created_block=(
            None if typed.get("created_block") is None else int(typed["created_block"])
        ),
        liq_id=None if typed.get("liq_id") is None else int(typed["liq_id"]),
        margin=None if typed.get("margin") is None else Decimal(str(typed["margin"])),
        payload=typed.get("payload"),
        position_id=None if typed.get("position_id") is None else int(typed["position_id"]),
        remark=typed.get("remark"),
        source=typed.get("source"),
        user=typed.get("user"),
        updated_at=typed.get("updated_at"),
    )
