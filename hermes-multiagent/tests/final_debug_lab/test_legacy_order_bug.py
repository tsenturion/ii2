import sqlite3
from datetime import date
from decimal import Decimal

from final_debug_lab.legacy_orders import get_order
from testing_lab.refunds import RefundService, ReturnRepository


def test_legacy_order_creates_refund_request():
    order = get_order(1002)
    connection = sqlite3.connect(":memory:")

    try:
        repository = ReturnRepository(connection)
        service = RefundService(repository)
        created = service.create_request(
            order=order,
            requested={101: 1},
            today=date(2026, 9, 20),
        )

        assert created["order_id"] == 1002
        assert created["amount"] == Decimal("90.00")
        assert created["status"] == "requested"
    finally:
        connection.close()
