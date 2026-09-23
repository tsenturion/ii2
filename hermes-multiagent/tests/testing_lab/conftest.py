import sqlite3
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from testing_lab.refunds import ReturnRepository


@pytest.fixture
def order_items():
    return [
        {
            "product_id": 101,
            "quantity": 3,
            "unit_price": Decimal("100.00"),
            "discount_percent": Decimal(10),
        },
        {
            "product_id": 202,
            "quantity": 2,
            "unit_price": Decimal("25.00"),
        },
        {
            "product_id": 303,
            "quantity": 2,
            "unit_price": Decimal("19.99"),
            "discount_percent": Decimal("12.5"),
        },
    ]


@pytest.fixture
def delivered_order(order_items):
    return {
        "id": 1001,
        "status": "delivered",
        "delivered_at": date(2026, 9, 1),
        "items": order_items,
    }


@pytest.fixture
def sqlite_connection():
    connection = sqlite3.connect(":memory:")
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def return_repository(sqlite_connection):
    return ReturnRepository(sqlite_connection)


@pytest.fixture
def mock_return_repository():
    repository = Mock(spec=ReturnRepository)
    repository.create.return_value = {
        "id": 1,
        "order_id": 1001,
        "amount": Decimal("25.00"),
        "status": "requested",
    }
    return repository
