class Calculator:
    """A calculator that works with floats."""

    def add(self, a, b):
        """Return a + b."""
        return float(a + b)

    def subtract(self, a, b):
        """Return a - b."""
        return float(a - b)

    def multiply(self, a, b):
        """Return a * b."""
        return float(a * b)

    def divide(self, a, b):
        """Return a / b. Raise ZeroDivisionError if b is 0."""
        if b == 0:
            raise ZeroDivisionError("division by zero")
        return float(a / b)
