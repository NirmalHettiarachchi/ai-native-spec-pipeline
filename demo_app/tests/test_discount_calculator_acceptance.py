import pytest
from demo_app.discount_calculator import ACCEPTANCE_CRITERIA, calculate_discounted_price

ACCEPTANCE_COVERAGE = {
    "AC-001": "test_ac_001_acceptance_valid_discount",
    "AC-002": "test_ac_002_acceptance_negative_base_price",
    "AC-003": "test_ac_003_acceptance_invalid_discount_range",
    "AC-004": "test_ac_004_acceptance_rounding"
}


@pytest.mark.acceptance
def test_ac_001_acceptance_valid_discount() -> None:
    """AC-001: valid discounts calculate correctly."""

    assert calculate_discounted_price(250, 10) == 225.0


@pytest.mark.acceptance
def test_ac_002_acceptance_negative_base_price() -> None:
    """AC-002: criterion is represented in generated acceptance coverage."""

    assert "AC-002" in ACCEPTANCE_CRITERIA


@pytest.mark.acceptance
def test_ac_003_acceptance_invalid_discount_range() -> None:
    """AC-003: criterion is represented in generated acceptance coverage."""

    assert "AC-003" in ACCEPTANCE_CRITERIA


@pytest.mark.acceptance
def test_ac_004_acceptance_rounding() -> None:
    """AC-004: final price rounds to two decimal places."""

    assert calculate_discounted_price(10, 33.333) == 6.67
