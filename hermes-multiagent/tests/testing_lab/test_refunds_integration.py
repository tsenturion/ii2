from decimal import Decimal

from testing_lab.refunds import RefundService, calculate_refund


def test_refund_request_is_saved_and_read_from_sqlite(
    delivered_order, return_repository
):
    requested = {101: 1, 303: 1}
    expected_amount = calculate_refund(delivered_order["items"], requested)
    service = RefundService(return_repository)

    created = service.create_request(
        delivered_order,
        requested,
        delivered_order["delivered_at"],
    )
    saved = return_repository.get(created["id"])

    assert saved is not None
    assert saved["order_id"] == delivered_order["id"]
    assert saved["amount"] == expected_amount == Decimal("107.49")
    assert saved["status"] == "requested"
