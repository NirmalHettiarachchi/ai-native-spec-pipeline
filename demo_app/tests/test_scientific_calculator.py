import math

import pytest

from demo_app import CalculatorError, run_scientific_calculator


# Test basic arithmetic operations
@pytest.mark.parametrize(
    "operation, operands, expected",
    [
        ("+", (1, 2), 3),
        ("-", (5, 3), 2),
        ("*", (2, 3), 6),
        ("/", (6, 3), 2),
    ],
)
def test_basic_operations(operation, operands, expected):
    assert run_scientific_calculator(operation, *operands) == expected


# Test division by zero
def test_division_by_zero():
    with pytest.raises(CalculatorError, match="Division by zero."):
        run_scientific_calculator("/", 4, 0)


# Test invalid operation
def test_invalid_operation():
    with pytest.raises(CalculatorError, match="Unsupported operation."):
        run_scientific_calculator("invalid", 1, 2)


# Test square root operation
def test_square_root():
    assert run_scientific_calculator("sqrt", 9) == 3


# Test logarithmic operation
def test_logarithm():
    assert run_scientific_calculator("log", math.e) == pytest.approx(1.0)


# Test trigonometric functions
@pytest.mark.parametrize(
    "operation, operand, expected",
    [
        ("sin", math.pi / 2, 1),
        ("cos", 0, 1),
        ("tan", math.pi / 4, 1),
    ],
)
def test_trigonometric_functions(operation, operand, expected):
    assert run_scientific_calculator(operation, operand) == pytest.approx(expected)
