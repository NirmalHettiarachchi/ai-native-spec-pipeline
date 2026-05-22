"""Convenience imports for running the generated demo app from the repo root."""

from importlib import import_module
from pathlib import Path

_SOURCE_PACKAGE = Path(__file__).resolve().parent / "src" / "demo_app"
__path__.append(str(_SOURCE_PACKAGE))

_discount_calculator = import_module(".discount_calculator", __name__)
DiscountValidationError = _discount_calculator.DiscountValidationError
calculate_discounted_price = _discount_calculator.calculate_discounted_price

__all__ = ["DiscountValidationError", "calculate_discounted_price"]
