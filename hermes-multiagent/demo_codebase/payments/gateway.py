class LegacyPaymentGateway:
    """Старый клиент платёжного сервиса."""

    def charge_legacy(self, order_id: int, amount: float) -> dict:
        return {
            "order_id": order_id,
            "amount": amount,
            "status": "paid",
            "gateway": "legacy",
        }


class PaymentGatewayV2:
    """Новый клиент платёжного сервиса."""

    def charge(self, order_id: int, amount: float) -> dict:
        return {
            "order_id": order_id,
            "amount": amount,
            "status": "paid",
            "gateway": "v2",
        }
