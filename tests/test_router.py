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
