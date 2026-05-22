class DiscountValidationError(Exception):
    """Exception raised for errors in the discount calculation input."""

    pass


def calculate_discounted_price(base_price: float, discount_percentage: float) -> float:
    """Calculate the discounted price given a base price and a discount percentage."""
    if base_price < 0:
        raise DiscountValidationError("AC-002: Base price cannot be negative.")
    if not (0 <= discount_percentage <= 100):
        raise DiscountValidationError(
            "AC-003: Discount percentage must be between 0 and 100 inclusive."
        )
    discounted_price = base_price * (1 - discount_percentage / 100)
    return round(discounted_price, 2)  # AC-004: Round to two decimal places


ACCEPTANCE_CRITERIA = [
    "AC-001: Calculate the discounted price for a valid base price and percentage.",
    "AC-002: Reject a negative base price.",
    "AC-003: Reject a discount percentage below 0 or above 100.",
    "AC-004: Round the final discounted price to two decimal places.",
]
