import pytest
from demo_app.discount_calculator import DiscountValidationError, calculate_discounted_price


def test_acceptance_criteria():
    # AC-001
    assert calculate_discounted_price(150, 25) == 112.50

    # AC-002
    with pytest.raises(DiscountValidationError, match="Base price cannot be negative."):
        calculate_discounted_price(-1, 50)

    # AC-003
    with pytest.raises(
        DiscountValidationError, match="Discount percentage must be between 0 and 100 inclusive."
    ):
        calculate_discounted_price(100, -1)
    with pytest.raises(
        DiscountValidationError, match="Discount percentage must be between 0 and 100 inclusive."
    ):
        calculate_discounted_price(100, 101)

    # AC-004
    assert calculate_discounted_price(250, 10) == 225.00
