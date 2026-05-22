import pytest
from demo_app import run_scientific_calculator


def test_ac_001_basic_arithmetic():
    assert run_scientific_calculator('10 + 5') == 15  # AC-001
    assert run_scientific_calculator('10 - 5') == 5
    assert run_scientific_calculator('10 * 5') == 50
    assert run_scientific_calculator('10 / 5') == 2


def test_ac_002_exponent_square_root():
    assert run_scientific_calculator('4 ^ 0.5') == 2  # AC-002
    assert run_scientific_calculator('sqrt 16') == 4


def test_ac_003_logarithm():
    assert run_scientific_calculator('log 1') == 0  # AC-003


def test_ac_004_trigonometric():
    assert run_scientific_calculator('sin 0') == 0  # AC-004
    assert run_scientific_calculator('cos 0') == 1
    assert run_scientific_calculator('tan 0') == 0


def test_ac_005_division_by_zero_error():
    with pytest.raises(ValueError, match='Division by zero'):
        run_scientific_calculator('10 / 0')  # AC-005


def test_ac_006_invalid_expression_error():
    with pytest.raises(ValueError, match='Invalid expression format'):
        run_scientific_calculator('invalid expression')  # AC-006
