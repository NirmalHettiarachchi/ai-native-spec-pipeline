import pytest
from demo_app import run_scientific_calculator


def test_addition():
    assert run_scientific_calculator('3 + 2') == 5


def test_subtraction():
    assert run_scientific_calculator('3 - 2') == 1


def test_multiplication():
    assert run_scientific_calculator('3 * 2') == 6


def test_division():
    assert run_scientific_calculator('4 / 2') == 2


def test_division_by_zero():
    with pytest.raises(ValueError, match='Division by zero'):
        run_scientific_calculator('4 / 0')


def test_exponentiation():
    assert run_scientific_calculator('2 ^ 3') == 8


def test_square_root():
    assert run_scientific_calculator('sqrt 9') == 3