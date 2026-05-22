import math

import pytest

from demo_app import CalculatorError, run_scientific_calculator


# Acceptance Test: AC-001 Basic Arithmetic
@pytest.mark.parametrize(
    "operation, operands, expected",
    [
        ("+", (1, 2), 3),
        ("-", (5, 3), 2),
        ("*", (2, 3), 6),
        ("/", (6, 3), 2),
    ],
)
def test_ac_001_basic_arithmetic(operation, operands, expected):
    assert run_scientific_calculator(operation, *operands) == expected


# Acceptance Test: AC-002 Exponent and Square Root
@pytest.mark.parametrize(
    "operation, operands, expected",
    [
        ("^", (2, 3), 8),
        ("sqrt", (9,), 3),
    ],
)
def test_ac_002_exponent_and_square_root(operation, operands, expected):
    assert run_scientific_calculator(operation, *operands) == expected


# Acceptance Test: AC-003 Logarithmic Operations
@pytest.mark.parametrize(
    "operand, expected",
    [
        (math.e, 1),
        (1, 0),
    ],
)
def test_ac_003_logarithmic_operations(operand, expected):
    assert run_scientific_calculator("log", operand) == pytest.approx(expected)


# Acceptance Test: AC-004 Trigonometric Functions
@pytest.mark.parametrize(
    "operation, operand, expected",
    [
        ("sin", 0, 0),
        ("cos", 0, 1),
        ("tan", math.pi / 4, 1),
    ],
)
def test_ac_004_trigonometric_functions(operation, operand, expected):
    assert run_scientific_calculator(operation, operand) == pytest.approx(expected)


# Acceptance Test: AC-005 Division by Zero
def test_ac_005_division_by_zero():
    with pytest.raises(CalculatorError, match="Division by zero."):
        run_scientific_calculator("/", 4, 0)


# Acceptance Test: AC-006 Invalid Expressions
def test_ac_006_invalid_expressions():
    with pytest.raises(CalculatorError, match="Unsupported operation."):
        run_scientific_calculator("invalid", 1, 2)
