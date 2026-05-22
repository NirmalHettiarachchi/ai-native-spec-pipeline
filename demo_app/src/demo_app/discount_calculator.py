class DiscountValidationError(Exception):
    pass


def calculate_discounted_price(base_price, discount_percentage):
    # Validate inputs
    if base_price < 0:
        raise DiscountValidationError("Base price cannot be negative.")

    if discount_percentage < 0 or discount_percentage > 100:
        raise DiscountValidationError("Discount percentage must be between 0 and 100 inclusive.")

    # Calculate discounted price
    discounted_price = base_price * (1 - discount_percentage / 100)
    # Round to two decimal places
    return round(discounted_price, 2)


ACCEPTANCE_CRITERIA = [
    "AC-001: Calculate the discounted price for a valid base price and percentage.",
    "AC-002: Reject a negative base price.",
    "AC-003: Reject a discount percentage below 0 or above 100.",
    "AC-004: Round the final discounted price to two decimal places.",
]
