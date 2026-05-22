"""Generated implementation for Scientific Calculator."""

from __future__ import annotations

import math
from collections.abc import Callable

Number = int | float

ACCEPTANCE_CRITERIA = ["AC-001", "AC-002", "AC-003", "AC-004", "AC-005", "AC-006"]


class CalculatorError(Exception):
    """Raised when a calculator expression violates supported operations."""


def run_scientific_calculator(expression: str, *operands: Number) -> Number:
    try:
        operation, arguments, expression_mode = _parse_expression(expression, operands)
        function = _operation(operation)
        if operation == "log" and expression_mode:
            return math.log10(arguments[0])
        return function(*arguments)
    except CalculatorError:
        raise
    except (IndexError, TypeError, ValueError, OverflowError) as exc:
        raise CalculatorError(f"Invalid expression: {exc}") from exc


def _parse_expression(
    expression: str, operands: tuple[Number, ...]
) -> tuple[str, list[float], bool]:
    if operands:
        return expression, [float(operand) for operand in operands], False
    parts = expression.split()
    return parts[0], [float(part) for part in parts[1:]], True


def _operation(operation: str) -> Callable[..., Number]:
    operations: dict[str, Callable[..., Number]] = {
        "*": lambda left, right: left * right,
        "+": lambda left, right: left + right,
        "-": lambda left, right: left - right,
        "/": _divide,
        "^": lambda left, right: left**right,
        "cos": math.cos,
        "log": math.log,
        "sin": math.sin,
        "sqrt": math.sqrt,
        "tan": math.tan,
    }
    try:
        return operations[operation]
    except KeyError as exc:
        raise CalculatorError(f"Unsupported operation: {operation}") from exc


def _divide(left: Number, right: Number) -> Number:
    if right == 0:
        raise CalculatorError("Division by zero.")
    return left / right
