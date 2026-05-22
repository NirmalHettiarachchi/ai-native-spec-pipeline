import pytest
from demo_app.discount_calculator import DiscountValidationError, calculate_discounted_price


def test_calculate_discounted_price():
    assert calculate_discounted_price(100, 10) == 90.00
    assert calculate_discounted_price(200, 20) == 160.00


def test_negative_base_price():
    with pytest.raises(DiscountValidationError, match="Base price cannot be negative."):
        calculate_discounted_price(-100, 20)


def test_discount_percentage_bounds():
    with pytest.raises(
        DiscountValidationError, match="Discount percentage must be between 0 and 100 inclusive."
    ):
        calculate_discounted_price(100, -10)

    with pytest.raises(
        DiscountValidationError, match="Discount percentage must be between 0 and 100 inclusive."
    ):
        calculate_discounted_price(100, 110)


def test_price_rounding():
    assert calculate_discounted_price(99.99, 10) == 89.99
    assert calculate_discounted_price(100.123, 10) == 90.11
