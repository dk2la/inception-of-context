import subprocess
import sys
from pathlib import Path

import pytest

from calculator.cli import parse_expression, run

TARGET_DIR = Path(__file__).parent.parent


def test_parse_simple_expression():
    assert parse_expression("2 + 3") == (2.0, "+", 3.0)


def test_parse_decimal_and_negative():
    assert parse_expression("1.5 * -2") == (1.5, "*", -2.0)


def test_parse_too_few_pieces():
    with pytest.raises(ValueError):
        parse_expression("2 +")


def test_parse_too_many_pieces():
    with pytest.raises(ValueError):
        parse_expression("2 + 3 + 4")


def test_parse_not_a_number():
    with pytest.raises(ValueError, match="not a number: a"):
        parse_expression("a + 3")


def test_parse_unknown_operator():
    with pytest.raises(ValueError, match="unknown operator: %"):
        parse_expression("2 % 3")


def test_run_adds(capsys):
    assert run(["2", "+", "3"]) == 0
    assert capsys.readouterr().out == "5\n"


def test_run_prints_decimals(capsys):
    assert run(["7", "/", "2"]) == 0
    assert capsys.readouterr().out == "3.5\n"


def test_run_negative_result(capsys):
    assert run(["2", "*", "-3"]) == 0
    assert capsys.readouterr().out == "-6\n"


def test_run_division_by_zero(capsys):
    assert run(["1", "/", "0"]) == 1
    assert capsys.readouterr().out == "error: division by zero\n"


def test_run_unknown_operator(capsys):
    assert run(["2", "%", "3"]) == 1
    assert capsys.readouterr().out.startswith("error:")


def test_run_without_arguments(capsys):
    assert run([]) == 1
    assert capsys.readouterr().out.startswith("error:")


def run_main(*args):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True, cwd=TARGET_DIR,
    )


def test_main_adds():
    result = run_main("2", "+", "3")
    assert result.stdout == "5\n"
    assert result.returncode == 0


def test_main_division_by_zero():
    result = run_main("1", "/", "0")
    assert result.stdout == "error: division by zero\n"
    assert result.returncode == 1
