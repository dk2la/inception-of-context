from calculator.core import Calculator

OPERATORS = ["+", "-", "*", "/"]


def parse_expression(text):
    """Read "2 + 3" and return (2.0, "+", 3.0)."""
    pieces = text.split()
    if len(pieces) != 3:
        raise ValueError("expected: <number> <operator> <number>")
    left, operator, right = pieces
    numbers = []
    for piece in (left, right):
        try:
            numbers.append(float(piece))
        except ValueError:
            raise ValueError(f"not a number: {piece}")
    if operator not in OPERATORS:
        raise ValueError(f"unknown operator: {operator}")
    return numbers[0], operator, numbers[1]


def run(args):
    """Print the result of the expression in args. Return 0, or 1 on error."""
    try:
        left, operator, right = parse_expression(" ".join(args))
    except ValueError as error:
        print(f"error: {error}")
        return 1
    calc = Calculator()
    methods = {"+": calc.add, "-": calc.subtract, "*": calc.multiply, "/": calc.divide}
    try:
        result = methods[operator](left, right)
    except ZeroDivisionError:
        print("error: division by zero")
        return 1
    if result.is_integer():
        result = int(result)
    print(result)
    return 0
