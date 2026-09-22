from demo_codebase.payments.gateway import LegacyPaymentGateway


def process_payment(order_id: int, amount: float) -> dict:
    """Выполняет списание оплаты за заказ."""

    gateway = LegacyPaymentGateway()

    return gateway.charge_legacy(
        order_id=order_id,
        amount=amount,
    )


def get_payment_provider_name() -> str:
    return "legacy-payment-provider"
