from decimal import Decimal
from typing import Any


def finite_decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("decimal value must be finite")
    return result
