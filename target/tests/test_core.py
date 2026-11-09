import pytest

from calculator.core import Calculator


def test_add():
    assert Calculator().add(2, 3) == 5.0


def test_add_negative():
    assert Calculator().add(-1, 1) == 0.0


def test_add_decimals():
    assert Calculator().add(0.1, 0.2) == pytest.approx(0.3)


def test_add_returns_float():
    assert type(Calculator().add(2, 3)) is float


def test_subtract():
    assert Calculator().subtract(10, 4) == 6.0


def test_subtract_negative_result():
    assert Calculator().subtract(4, 10) == -6.0


def test_multiply():
    assert Calculator().multiply(4, 2.5) == 10.0


def test_multiply_negative():
    assert Calculator().multiply(-3, 3) == -9.0


def test_multiply_by_zero():
    assert Calculator().multiply(7, 0) == 0.0


def test_multiply_returns_float():
    assert type(Calculator().multiply(2, 3)) is float


def test_divide():
    assert Calculator().divide(7, 2) == 3.5


def test_divide_negative():
    assert Calculator().divide(-9, 3) == -3.0


def test_divide_zero_numerator():
    assert Calculator().divide(0, 5) == 0.0


def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        Calculator().divide(1, 0)


def test_divide_by_float_zero():
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        Calculator().divide(1, 0.0)
