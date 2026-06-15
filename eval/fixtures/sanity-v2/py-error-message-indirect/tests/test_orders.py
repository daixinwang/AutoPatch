import pytest

from orders.api import create_order


def test_invalid_quantity_mentions_field_name():
    with pytest.raises(ValueError, match="quantity must be a positive integer"):
        create_order(12.5, 0)


def test_valid_order_total():
    assert create_order(12.5, 3) == {"total": 37.5}
