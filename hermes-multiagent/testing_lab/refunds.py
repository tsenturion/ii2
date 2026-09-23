from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal


def calculate_refund(
    items: list[dict],
    requested: dict[int, int],
) -> Decimal:
    """Рассчитывает сумму возврата по выбранным позициям."""

    if not requested:
        raise ValueError("Не выбраны позиции для возврата")

    items_by_product = {item["product_id"]: item for item in items}
    total = Decimal(0)

    for product_id, requested_quantity in requested.items():
        if product_id not in items_by_product:
            raise ValueError("Товар отсутствует в заказе")

        if requested_quantity <= 0:
            raise ValueError("Количество должно быть больше нуля")

        item = items_by_product[product_id]

        if requested_quantity > item["quantity"]:
            raise ValueError("Нельзя вернуть больше товара, чем было куплено")

        unit_price = Decimal(str(item["unit_price"]))
        discount_percent = Decimal(str(item.get("discount_percent", 0)))
        paid_unit_price = (
            unit_price * (Decimal(100) - discount_percent) / Decimal(100)
        )
        total += paid_unit_price * requested_quantity

    return total.quantize(Decimal("0.01"))


class ReturnRepository:
    """Хранилище заявок на возврат."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def create(self, order_id: int, amount: Decimal) -> dict:
        cursor = self.connection.execute(
            """
            INSERT INTO returns (
                order_id,
                amount,
                status
            )
            VALUES (?, ?, ?)
            """,
            (order_id, str(amount), "requested"),
        )
        self.connection.commit()
        return self.get(cursor.lastrowid)

    def get(self, return_id: int) -> dict | None:
        cursor = self.connection.execute(
            """
            SELECT
                id,
                order_id,
                amount,
                status
            FROM returns
            WHERE id = ?
            """,
            (return_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "order_id": row[1],
            "amount": Decimal(row[2]),
            "status": row[3],
        }


class RefundService:
    """Создаёт заявку на возврат."""

    def __init__(self, repository: ReturnRepository) -> None:
        self.repository = repository

    def create_request(
        self,
        order: dict,
        requested: dict[int, int],
        today: date,
    ) -> dict:
        if order["status"] != "delivered":
            raise ValueError("Возврат доступен только для полученного заказа")

        delivered_at = order.get("delivered_at")

        if delivered_at is None:
            raise ValueError("Дата получения заказа неизвестна")

        days_since_delivery = (today - delivered_at).days

        if days_since_delivery < 0:
            raise ValueError("Дата получения не может быть в будущем")

        if days_since_delivery > 14:
            raise ValueError("Срок возврата истёк")

        amount = calculate_refund(order["items"], requested)
        return self.repository.create(order_id=order["id"], amount=amount)
