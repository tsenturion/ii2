from datetime import timedelta
from decimal import Decimal

import pytest

from testing_lab.refunds import RefundService, calculate_refund


def test_calculate_refund_uses_price_from_order(order_items):
    amount = calculate_refund(order_items, {202: 2})

    assert amount == Decimal("50.00")


def test_calculate_refund_supports_partial_quantity(order_items):
    amount = calculate_refund(order_items, {101: 1})

    assert amount == Decimal("90.00")


def test_calculate_refund_allows_returning_all_purchased_quantity(order_items):
    amount = calculate_refund(order_items, {101: 3})

    assert amount == Decimal("270.00")


def test_calculate_refund_applies_saved_discount_and_rounds_to_cents(order_items):
    amount = calculate_refund(order_items, {303: 1})

    assert amount == Decimal("17.49")


def test_calculate_refund_sums_multiple_positions(order_items):
    amount = calculate_refund(order_items, {101: 2, 202: 1, 303: 1})

    assert amount == Decimal("222.49")


def test_calculate_refund_rejects_empty_request(order_items):
    with pytest.raises(ValueError):
        calculate_refund(order_items, {})


def test_calculate_refund_rejects_product_not_in_order(order_items):
    with pytest.raises(ValueError):
        calculate_refund(order_items, {999: 1})


@pytest.mark.parametrize("quantity", [0, -1])
def test_calculate_refund_rejects_nonpositive_quantity(order_items, quantity):
    with pytest.raises(ValueError):
        calculate_refund(order_items, {101: quantity})


def test_calculate_refund_rejects_quantity_above_purchased(order_items):
    with pytest.raises(ValueError):
        calculate_refund(order_items, {101: 4})


def test_refund_service_rejects_order_with_wrong_status(
    delivered_order, mock_return_repository
):
    delivered_order["status"] = "processing"
    service = RefundService(mock_return_repository)

    with pytest.raises(ValueError):
        service.create_request(
            delivered_order, {202: 1}, delivered_order["delivered_at"]
        )

    mock_return_repository.create.assert_not_called()


def test_refund_service_rejects_order_without_delivery_date(
    delivered_order, mock_return_repository
):
    delivered_order["delivered_at"] = None
    service = RefundService(mock_return_repository)

    with pytest.raises(ValueError):
        service.create_request(delivered_order, {202: 1}, delivered_order["delivered_at"])

    mock_return_repository.create.assert_not_called()


def test_refund_service_rejects_delivery_date_in_future(
    delivered_order, mock_return_repository
):
    today = delivered_order["delivered_at"]
    delivered_order["delivered_at"] = today + timedelta(days=1)
    service = RefundService(mock_return_repository)

    with pytest.raises(ValueError):
        service.create_request(delivered_order, {202: 1}, today)

    mock_return_repository.create.assert_not_called()


def test_refund_service_accepts_return_within_allowed_period(
    delivered_order, mock_return_repository
):
    today = delivered_order["delivered_at"] + timedelta(days=13)
    service = RefundService(mock_return_repository)

    service.create_request(delivered_order, {202: 1}, today)

    mock_return_repository.create.assert_called_once_with(
        order_id=delivered_order["id"], amount=Decimal("25.00")
    )


def test_refund_service_accepts_return_on_fourteenth_day(
    delivered_order, mock_return_repository
):
    today = delivered_order["delivered_at"] + timedelta(days=14)
    service = RefundService(mock_return_repository)

    service.create_request(delivered_order, {202: 1}, today)

    mock_return_repository.create.assert_called_once_with(
        order_id=delivered_order["id"], amount=Decimal("25.00")
    )


def test_refund_service_rejects_return_after_allowed_period(
    delivered_order, mock_return_repository
):
    today = delivered_order["delivered_at"] + timedelta(days=15)
    service = RefundService(mock_return_repository)

    with pytest.raises(ValueError):
        service.create_request(delivered_order, {202: 1}, today)

    mock_return_repository.create.assert_not_called()
