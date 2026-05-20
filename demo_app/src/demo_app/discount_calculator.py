"""Generated implementation for Discount Calculator."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Number = int | float | Decimal

ACCEPTANCE_CRITERIA = {
    "AC-001": "Calculate the discounted price for a valid base price and percentage.",
    "AC-002": "Reject a negative base price.",
    "AC-003": "Reject a discount percentage below 0 or above 100.",
    "AC-004": "Round the final discounted price to two decimal places."
}


class DiscountValidationError(ValueError):
    """Raised when discount inputs violate approved business rules."""


def calculate_discounted_price(base_price: Number, discount_percent: Number) -> float:
    """Calculate a discounted price using approved business rules."""

    price = _to_decimal(base_price, "base_price")
    discount = _to_decimal(discount_percent, "discount_percent")

    if price < Decimal("0"):
        raise DiscountValidationError("base price must be greater than or equal to zero")
    if discount < Decimal("0") or discount > Decimal("100"):
        raise DiscountValidationError("discount percentage must be between 0 and 100")

    multiplier = Decimal("1") - (discount / Decimal("100"))
    final_price = price * multiplier
    return float(final_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _to_decimal(value: Number, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DiscountValidationError(f"{field_name} must be numeric") from exc
