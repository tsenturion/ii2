from demo_codebase.payments.service import process_payment


def checkout(order: dict) -> dict:
    """Завершает оформление заказа и инициирует оплату."""

    payment = process_payment(
        order_id=order["id"],
        amount=order["total"],
    )

    return {
        "order": order,
        "payment": payment,
    }
