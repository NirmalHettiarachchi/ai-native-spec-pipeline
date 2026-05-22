import pytest

from demo_app import DiscountValidationError, calculate_discounted_price


def test_calculate_discounted_price_valid():
    assert calculate_discounted_price(100, 20) == 80.0  # AC-001
    assert calculate_discounted_price(50, 50) == 25.0  # AC-001


def test_calculate_discounted_price_rounding():
    assert calculate_discounted_price(100, 33.3333) == 66.67  # AC-004


@pytest.mark.parametrize(
    "base_price,discount_percentage",
    [
        (-10, 10),  # AC-002
        (100, -1),  # AC-003
        (100, 101),  # AC-003
    ],
)
def test_calculate_discounted_price_invalid(base_price, discount_percentage):
    with pytest.raises(DiscountValidationError):
        calculate_discounted_price(base_price, discount_percentage)
