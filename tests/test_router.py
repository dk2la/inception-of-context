import pytest

from p2.ask import route_question


# --- "is there a function X?" ---


@pytest.mark.parametrize("question, name", [
    ("Is there a function power?", "power"),
    ("is there a method divide", "divide"),
    ("Is there any function called `add`?", "add"),
    ("is there an function named subtract", "subtract"),
    ("is there function power", "power"),
    ("IS THERE A FUNCTION Multiply?", "Multiply"),
    ("  Is there a function power ?  ", "power"),
    ("Is there a function power.", "power"),
    ("Is there a function called power in the project?", "power"),
    ("Is there a method Calculator.divide?", "Calculator.divide"),
])
def test_is_there_a_function_is_recognised(question, name):
    assert route_question(question) == ("has_function", name)


@pytest.mark.parametrize("question, name", [
    ("Does a function sqrt exist?", "sqrt"),
    ("does function sqrt exist", "sqrt"),
    ("Does the method `divide` exist?", "divide"),
    ("Does any function power exist in the project?", "power"),
])
def test_does_a_function_exist_is_recognised(question, name):
    assert route_question(question) == ("has_function", name)


@pytest.mark.parametrize("question", [
    "How does divide handle zero?",
    "How does division work?",
    "Explain the CLI",
    "",
    "Is there a README?",
    "Is there a function that divides numbers?",
    "Is there a function to compute a power?",
    "Is there a method for dividing two numbers?",
    "Is there a function called add or subtract?",
    "Is there a function in core.py that handles zero?",
    "Does the function divide raise an error?",
    "Does divide exist?",
])
def test_other_questions_are_left_to_the_model(question):
    assert route_question(question) is None


# --- "what functions are in file Y?" ---


@pytest.mark.parametrize("question, filename", [
    ("What functions are in core.py?", "core.py"),
    ("what methods are defined in calculator/cli.py", "calculator/cli.py"),
    ("Which functions does `main.py` have?", "main.py"),
    ("List the functions in core.py.", "core.py"),
    ("What functions are there in the file core.py?", "core.py"),
    ("Which functions are in `calculator/core.py`?", "calculator/core.py"),
    ("which methods does core.py contain", "core.py"),
    ("What are the functions in core.py?", "core.py"),
    ("Show me all the methods in core.py", "core.py"),
    ("WHAT FUNCTIONS ARE IN Core.py?", "Core.py"),
    ("What functions are in my-tests/test_core.py?", "my-tests/test_core.py"),
])
def test_what_functions_are_in_a_file_is_recognised(question, filename):
    assert route_question(question) == ("file_functions", filename)


@pytest.mark.parametrize("question", [
    "What does the function in cli.py do?",
    "What functions does the CLI use?",
    "What functions are in the project?",
    "What functions are used in core.py to handle zero?",
    "What functions are in core.py that raise errors?",
    "What is in core.py?",
    "Explain core.py",
    "Which functions call divide in core.py?",
])
def test_other_questions_about_a_file_are_left_to_the_model(question):
    assert route_question(question) is None


def test_the_two_kinds_of_question_do_not_get_mixed_up():
    assert route_question("Is there a function power?") == ("has_function", "power")
    assert route_question("Is there a function in core.py?") is None
