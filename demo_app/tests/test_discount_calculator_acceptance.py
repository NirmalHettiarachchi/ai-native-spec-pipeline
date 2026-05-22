import pytest

from demo_app import DiscountValidationError, calculate_discounted_price


# AC-001
def test_acceptance_calculate_valid_discount():
    assert calculate_discounted_price(200, 10) == 180.0


# AC-002
def test_acceptance_reject_negative_base_price():
    with pytest.raises(DiscountValidationError, match=r"AC-002"):
        calculate_discounted_price(-50, 10)


# AC-003
@pytest.mark.parametrize("discount_percentage", [-5, 105])
def test_acceptance_reject_invalid_discount_percentage(discount_percentage):
    with pytest.raises(DiscountValidationError, match=r"AC-003"):
        calculate_discounted_price(100, discount_percentage)


# AC-004
def test_acceptance_rounding():
    assert calculate_discounted_price(250, 66.6667) == 83.33
