def send_order_email(email: str, order_id: int) -> str:
    """Формирует уведомление о заказе."""

    return f"Уведомление о заказе {order_id} отправлено на {email}"
