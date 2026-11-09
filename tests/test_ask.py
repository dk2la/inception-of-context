import os

import pytest

from p1.index import reindex_file
from p2 import ask

CALC = '''class Calculator:
    def add(self, a, b):
        return a + b

    def divide(self, a, b):
        return a / b
'''

OTHER = '''import os


def greet():
    return "hi"
'''


def index_files(target, files):
    """Write files into the temporary Target Project and index them."""
    for name, text in files.items():
        path = os.path.join(target, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        reindex_file(path)


# --- known_symbols ---


def test_known_symbols_lists_the_whole_file_of_the_chunk(temp_index):
    index_files(temp_index, {"calc.py": CALC, "other.py": OTHER})
    symbols = ask.known_symbols([{"path": "calc.py"}])
    assert symbols == [
        "calc.py: Calculator (class)",
        "calc.py: Calculator.add (method)",
        "calc.py: Calculator.divide (method)",
    ]


def test_known_symbols_covers_every_file_given(temp_index):
    index_files(temp_index, {"calc.py": CALC, "other.py": OTHER})
    symbols = ask.known_symbols([{"path": "calc.py"}, {"path": "other.py"}])
    assert "calc.py: Calculator.add (method)" in symbols
    assert "other.py: greet (function)" in symbols


def test_known_symbols_leaves_out_the_module_header(temp_index):
    index_files(temp_index, {"other.py": OTHER})
    assert ask.known_symbols([{"path": "other.py"}]) == ["other.py: greet (function)"]


def test_known_symbols_has_no_duplicates_and_is_sorted(temp_index):
    index_files(temp_index, {"calc.py": CALC})
    once = ask.known_symbols([{"path": "calc.py"}])
    twice = ask.known_symbols([{"path": "calc.py"}, {"path": "calc.py"}])
    assert twice == once
    assert once == sorted(once)


def test_known_symbols_of_no_chunks_is_empty(temp_index):
    assert ask.known_symbols([]) == []


def test_known_symbols_ignores_headings_and_config_keys(temp_index):
    index_files(temp_index, {"README.md": "# divide\n\ntext\n", "app.yml": "name: x\n"})
    assert ask.known_symbols([{"path": "README.md"}, {"path": "app.yml"}]) == []


# --- build_answer_prompt ---

DIVIDE = {
    "path": "calc.py", "start_line": 5, "end_line": 6, "name": "Calculator.divide",
    "text": "    def divide(self, a, b):\n        return a / b",
}
GREET = {
    "path": "other.py", "start_line": 4, "end_line": 5, "name": "greet",
    "text": "def greet():\n    return 'hi'",
}
SYMBOLS = ["calc.py: Calculator (class)", "calc.py: Calculator.divide (method)"]


def test_prompt_contains_the_question_the_symbols_and_every_chunk():
    prompt = ask.build_answer_prompt("How does division work?", [DIVIDE, GREET], SYMBOLS)
    assert "How does division work?" in prompt
    for line in SYMBOLS:
        assert line in prompt
    assert "--- calc.py lines 5-6 (Calculator.divide) ---" in prompt
    assert DIVIDE["text"] in prompt
    assert "--- other.py lines 4-5 (greet) ---" in prompt
    assert GREET["text"] in prompt


def test_prompt_sections_come_in_order_and_it_ends_with_answer():
    prompt = ask.build_answer_prompt("How does division work?", [DIVIDE], SYMBOLS)
    assert prompt.index("KNOWN SYMBOLS:") < prompt.index("CODE:") < prompt.index("QUESTION:")
    assert prompt.endswith("ANSWER:")


def test_prompt_says_none_when_there_are_no_symbols():
    prompt = ask.build_answer_prompt("anything?", [], [])
    assert "KNOWN SYMBOLS:\n(none)" in prompt


def test_prompt_never_contains_the_patch_file_marker():
    prompt = ask.build_answer_prompt("What is in calc.py?", [DIVIDE, GREET], SYMBOLS)
    assert "=== FILE:" not in prompt


# --- find_symbol ---

SUBDIVIDE = "def subdivide(n):\n    return n / 2\n"


def index_for_find(target):
    index_files(target, {"calc.py": CALC, "parts.py": SUBDIVIDE, "notes.md": "# divide\n\nAbout dividing.\n"})


def test_find_symbol_matches_a_method_by_its_short_name(temp_index):
    index_for_find(temp_index)
    found = ask.find_symbol("divide")
    assert [(c["name"], c["kind"]) for c in found] == [("Calculator.divide", "method")]


def test_find_symbol_does_not_match_part_of_a_name(temp_index):
    index_for_find(temp_index)
    assert "subdivide" not in [c["name"] for c in ask.find_symbol("divide")]
    assert ask.find_symbol("divid") == []


def test_find_symbol_finds_a_function_and_a_class(temp_index):
    index_for_find(temp_index)
    assert [c["name"] for c in ask.find_symbol("subdivide")] == ["subdivide"]
    assert [(c["name"], c["kind"]) for c in ask.find_symbol("Calculator")] == [("Calculator", "class")]


def test_find_symbol_of_a_missing_name_is_empty(temp_index):
    index_for_find(temp_index)
    assert ask.find_symbol("power") == []


def test_find_symbol_is_case_sensitive(temp_index):
    index_for_find(temp_index)
    assert ask.find_symbol("Divide") == []
    assert ask.find_symbol("calculator") == []


def test_find_symbol_ignores_headings(temp_index):
    index_files(temp_index, {"notes.md": "# divide\n\nAbout dividing.\n"})
    assert ask.find_symbol("divide") == []


def test_find_symbol_returns_chunk_dictionaries(temp_index):
    index_for_find(temp_index)
    chunk = ask.find_symbol("divide")[0]
    for key in ["id", "text", "path", "start_line", "end_line", "name", "kind"]:
        assert key in chunk
    assert chunk["path"] == "calc.py"
    assert (chunk["start_line"], chunk["end_line"]) == (5, 6)
    assert "return a / b" in chunk["text"]


def test_find_symbol_lists_every_match_in_path_and_line_order(temp_index):
    index_files(temp_index, {"b.py": "def run():\n    pass\n", "a.py": "class A:\n    def run(self):\n        pass\n\n\ndef run():\n    pass\n"})
    found = ask.find_symbol("run")
    assert [(c["path"], c["name"]) for c in found] == [("a.py", "A.run"), ("a.py", "run"), ("b.py", "run")]


# --- symbols_in_file ---

CORE_METHODS = ["Calculator.add", "Calculator.subtract", "Calculator.multiply", "Calculator.divide"]


def test_symbols_in_core_py_are_exactly_the_four_methods_in_source_order(client):
    assert [c["name"] for c in ask.symbols_in_file("core.py")] == CORE_METHODS


def test_symbols_in_file_accepts_the_full_path(client):
    assert [c["name"] for c in ask.symbols_in_file("calculator/core.py")] == CORE_METHODS


def test_symbols_in_file_leaves_out_classes(client):
    assert "class" not in [c["kind"] for c in ask.symbols_in_file("core.py")]


def test_symbols_in_file_does_not_match_a_longer_file_name(temp_index):
    index_files(temp_index, {"hardcore.py": "def x():\n    pass\n", "core.py": "def y():\n    pass\n"})
    assert [c["name"] for c in ask.symbols_in_file("core.py")] == ["y"]


def test_symbols_in_file_of_a_missing_file_is_empty(client):
    assert ask.symbols_in_file("nope.py") == []


def test_symbols_in_file_ignores_backticks_and_spaces(client):
    assert ask.symbols_in_file("`core.py`") == ask.symbols_in_file("core.py")
    assert ask.symbols_in_file(" `core.py` ") == ask.symbols_in_file("core.py")


def test_symbols_in_file_shows_both_files_that_share_a_short_name(temp_index):
    index_files(temp_index, {"a/utils.py": "def one():\n    pass\n", "b/utils.py": "def two():\n    pass\n"})
    found = ask.symbols_in_file("utils.py")
    assert [(c["path"], c["name"]) for c in found] == [("a/utils.py", "one"), ("b/utils.py", "two")]


# --- ask: a free Question goes through the model ---


def test_ask_returns_the_models_answer_without_surrounding_whitespace(client, fake_llm):
    fake_llm.replies = ["  Division is in Calculator.divide.  "]
    result = ask.ask("How does division work?")
    assert result["answer"] == "Division is in Calculator.divide."
    assert result["used_llm"] is True


def test_ask_uses_the_answer_model_in_plain_text_mode(client, fake_llm):
    fake_llm.replies = ["ok"]
    ask.ask("How does division work?")
    model, _, json_mode = fake_llm.prompts[0]
    assert model == ask.ANSWER_MODEL
    assert json_mode is False


def test_ask_prompt_has_the_question_the_symbols_and_the_code(client, fake_llm):
    fake_llm.replies = ["ok"]
    ask.ask("How does division work?")
    prompt = fake_llm.prompts[0][1]
    assert "How does division work?" in prompt
    assert "KNOWN SYMBOLS:" in prompt
    assert "calculator/core.py: Calculator.divide (method)" in prompt
    assert "def divide" in prompt


def test_ask_sources_are_the_chunks_given_to_the_model(client, fake_llm):
    fake_llm.replies = ["ok"]
    result = ask.ask("How does division work?", k=2)
    assert len(result["sources"]) == 2
    for source in result["sources"]:
        assert source["text"] in fake_llm.prompts[0][1]
        assert "path" in source


def test_ask_does_not_call_the_model_when_nothing_is_indexed(temp_index, fake_llm):
    result = ask.ask("How does division work?")
    assert result["used_llm"] is False
    assert result["sources"] == []
    assert "Index is empty" in result["answer"]
    assert fake_llm.prompts == []


def test_ask_lets_a_model_error_through(client, fake_llm):
    fake_llm.error = ask.LLMError("Ollama is not reachable")
    with pytest.raises(ask.LLMError):
        ask.ask("How does division work?")


# --- ask: symbol questions are answered from the Index, without the model ---


def test_a_missing_function_is_answered_no_without_the_model(client, fake_llm):
    fake_llm.replies = ["Yes, power exists"]  # the model must not even be asked
    result = ask.ask("Is there a function power?")
    assert result["answer"].startswith("No")
    assert '"power"' in result["answer"]
    assert result["sources"] == []
    assert result["used_llm"] is False
    assert fake_llm.prompts == []


def test_an_existing_method_is_answered_yes_with_its_place(client, fake_llm):
    result = ask.ask("Is there a function add?")
    assert result["answer"].startswith("Yes")
    assert "method Calculator.add in calculator/core.py, lines 4-6" in result["answer"]
    assert [s["name"] for s in result["sources"]] == ["Calculator.add"]
    assert result["used_llm"] is False
    assert fake_llm.prompts == []


def test_every_match_of_a_name_is_listed_on_its_own_line(temp_index, fake_llm):
    index_files(temp_index, {"a.py": "def run():\n    pass\n", "b.py": "class B:\n    def run(self):\n        pass\n"})
    result = ask.ask("Is there a function run?")
    assert "- function run in a.py, lines 1-2" in result["answer"]
    assert "- method B.run in b.py, lines 2-3" in result["answer"]
    assert len(result["sources"]) == 2


CORE_ANSWER = ("calculator/core.py defines 4 functions: "
               "Calculator.add, Calculator.subtract, Calculator.multiply, Calculator.divide.")


def test_the_functions_of_core_py_are_exactly_the_four_methods(client, fake_llm):
    result = ask.ask("What functions are in core.py?")
    assert result["answer"] == CORE_ANSWER
    assert [s["name"] for s in result["sources"]] == CORE_METHODS
    assert {s["path"] for s in result["sources"]} == {"calculator/core.py"}
    assert result["used_llm"] is False
    assert fake_llm.prompts == []


def test_the_same_question_in_russian_gives_the_same_answer(client, fake_llm):
    result = ask.ask("Какие функции есть в файле core.py?")
    assert result["answer"] == CORE_ANSWER
    assert [s["name"] for s in result["sources"]] == CORE_METHODS
    assert result["used_llm"] is False
    assert fake_llm.prompts == []


def test_a_file_without_functions_is_answered_clearly(client, fake_llm):
    result = ask.ask("What functions are in nope.py?")
    assert result["answer"] == 'I found no functions in a file named "nope.py".'
    assert result["sources"] == []
    assert result["used_llm"] is False
    assert fake_llm.prompts == []


def test_a_file_with_one_function_says_function_not_functions(temp_index, fake_llm):
    index_files(temp_index, {"one.py": "def only():\n    pass\n"})
    assert ask.ask("What functions are in one.py?")["answer"] == "one.py defines 1 function: only."


def test_two_files_with_the_same_short_name_are_both_shown(temp_index, fake_llm):
    index_files(temp_index, {"a/utils.py": "def one():\n    pass\n", "b/utils.py": "def two():\n    pass\n"})
    answer = ask.ask("What functions are in utils.py?")["answer"]
    assert answer == "a/utils.py defines 1 function: one.\nb/utils.py defines 1 function: two."


def test_a_question_that_only_looks_like_a_symbol_question_still_goes_to_the_model(client, fake_llm):
    fake_llm.replies = ["It raises ZeroDivisionError."]
    result = ask.ask("How does divide handle zero?")
    assert result["answer"] == "It raises ZeroDivisionError."
    assert result["used_llm"] is True
    assert len(fake_llm.prompts) == 1
