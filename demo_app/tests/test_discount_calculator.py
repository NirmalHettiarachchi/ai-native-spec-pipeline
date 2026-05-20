import pytest
from demo_app.discount_calculator import DiscountValidationError, calculate_discounted_price

import demo_app


def test_ac_001_calculates_discounted_price() -> None:
    """AC-001: valid base price and percentage produce a discounted price."""

    assert calculate_discounted_price(100, 15) == 85.0


def test_ac_002_rejects_negative_base_price() -> None:
    """AC-002: negative base prices are rejected."""

    with pytest.raises(DiscountValidationError, match="base price"):
        calculate_discounted_price(-1, 10)


def test_ac_003_rejects_invalid_discount_range() -> None:
    """AC-003: discount percentage must be between 0 and 100."""

    with pytest.raises(DiscountValidationError, match="between 0 and 100"):
        calculate_discounted_price(100, -0.01)
    with pytest.raises(DiscountValidationError, match="between 0 and 100"):
        calculate_discounted_price(100, 100.01)


def test_integration_package_export() -> None:
    assert demo_app.calculate_discounted_price(40, 25) == 30.0
