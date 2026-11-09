import os

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
