import math

ACCEPTANCE_CRITERIA = [
    'AC-001: Evaluate basic arithmetic expressions correctly.',
    'AC-002: Evaluate exponent and square root operations correctly.',
    'AC-003: Evaluate logarithmic operations correctly.',
    'AC-004: Evaluate sine, cosine, and tangent in radians correctly.',
    'AC-005: Reject division by zero with a validation error.',
    'AC-006: Reject invalid or unsupported expressions with a validation error.'
]

ALLOWED_OPERATIONS = {
    '+': lambda x, y: x + y,
    '-': lambda x, y: x - y,
    '*': lambda x, y: x * y,
    '/': lambda x, y: x / y if y != 0 else (_ for _ in ()).throw(ZeroDivisionError('Division by zero')),
    '^': lambda x, y: x ** y,
    'sqrt': lambda x: math.sqrt(x),
    'log': lambda x: math.log(x),
    'sin': lambda x: math.sin(x),
    'cos': lambda x: math.cos(x),
    'tan': lambda x: math.tan(x),
}


def run_scientific_calculator(expression: str):
    elements = expression.split()
    if len(elements) == 3 and elements[0].isdigit() and elements[2].isdigit():
        op, x, y = elements[1], float(elements[0]), float(elements[2])
    elif len(elements) == 2 and elements[1].isdigit():
        op, x = elements
        x = float(x)
    else:
        raise ValueError('Invalid expression format')

    if op in ALLOWED_OPERATIONS:
        try:
            return round(ALLOWED_OPERATIONS[op](x, y), 10) if len(elements) == 3 else round(ALLOWED_OPERATIONS[op](x), 10)
        except ZeroDivisionError as e:
            raise ValueError('Division by zero') from e
    else:
        raise ValueError('Unsupported operation')
