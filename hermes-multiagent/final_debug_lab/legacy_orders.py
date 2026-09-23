from copy import deepcopy
from datetime import date
from decimal import Decimal

_ORDERS = {
    1001: {
        "id": 1001,
        "status": "delivered",
        "delivered_at": date(2026, 9, 10),
        "items": [
            {
                "product_id": 101,
                "quantity": 2,
                "unit_price": Decimal("100.00"),
                "discount_percent": Decimal(10),
            }
        ],
    },
    1002: {
        "id": 1002,
        "status": "delivered",
        "delivered_at": "2026-09-10",
        "items": [
            {
                "product_id": 101,
                "quantity": 2,
                "unit_price": Decimal("100.00"),
                "discount_percent": Decimal(10),
            }
        ],
    },
}


def get_order(order_id: int) -> dict:
    """Возвращает независимую копию заказа из legacy-источника."""

    if order_id not in _ORDERS:
        raise KeyError(f"Заказ {order_id} не найден")

    order = deepcopy(_ORDERS[order_id])
    if isinstance(order.get("delivered_at"), str):
        order["delivered_at"] = date.fromisoformat(order["delivered_at"])

    return order
