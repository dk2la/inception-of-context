import os

from p1.chunker import (
    chunk_by_regex,
    chunk_file,
    chunk_markdown,
    chunk_python,
    chunk_yaml,
    make_chunk,
)

# --- make_chunk ---


def test_make_chunk_has_exactly_the_seven_keys():
    chunk = make_chunk("a.py", 1, 2, "f", "function", "def f():\n    pass")
    assert chunk == {
        "path": "a.py",
        "start_line": 1,
        "end_line": 2,
        "name": "f",
        "kind": "function",
        "text": "def f():\n    pass",
        "hash": chunk["hash"],
    }
    assert len(chunk["hash"]) == 64


def test_hash_depends_only_on_text():
    a = make_chunk("a.py", 1, 1, "f", "function", "x = 1")
    b = make_chunk("b.py", 9, 9, "g", "module", "x = 1")
    c = make_chunk("a.py", 1, 1, "f", "function", "x = 2")
    assert a["hash"] == b["hash"]
    assert a["hash"] != c["hash"]


# --- top-level functions ---

TWO_FUNCTIONS = '''import sys

def hello():
    print("hi")

async def fetch():
    return 1
'''


def functions_only(chunks):
    return [c for c in chunks if c["kind"] != "module"]


def test_one_chunk_per_top_level_function():
    chunks = functions_only(chunk_python("main.py", TWO_FUNCTIONS))
    assert [(c["name"], c["kind"], c["start_line"], c["end_line"]) for c in chunks] == [
        ("hello", "function", 3, 4),
        ("fetch", "async_function", 6, 7),
    ]
    assert chunks[0]["text"] == 'def hello():\n    print("hi")'
    assert chunks[0]["path"] == "main.py"


def test_empty_text_gives_no_chunks():
    assert chunk_python("a.py", "") == []
    assert chunk_python("a.py", "  \n\n") == []


def test_multiline_signature_is_one_chunk():
    text = "def add(\n    a,\n    b,\n):\n    return a + b\n"
    [chunk] = chunk_python("a.py", text)
    assert (chunk["start_line"], chunk["end_line"]) == (1, 5)
    assert "    b,\n):" in chunk["text"]


def test_nested_function_is_not_a_chunk():
    text = "def outer():\n    def inner():\n        pass\n    return inner\n"
    chunks = chunk_python("a.py", text)
    assert [c["name"] for c in chunks] == ["outer"]


# --- classes and methods ---

CALCULATOR = '''class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
'''


def summary(chunks):
    return [(c["name"], c["kind"], c["start_line"], c["end_line"]) for c in chunks]


def test_class_and_its_methods_are_chunks():
    assert summary(chunk_python("a.py", CALCULATOR)) == [
        ("Calculator", "class", 1, 6),
        ("Calculator.add", "method", 2, 3),
        ("Calculator.subtract", "method", 5, 6),
    ]


def test_method_text_is_exactly_its_own_lines():
    method = chunk_python("a.py", CALCULATOR)[1]
    assert method["text"] == "    def add(self, a, b):\n        return a + b"


def test_class_without_methods_is_one_chunk():
    assert summary(chunk_python("a.py", "class Empty:\n    pass\n")) == [("Empty", "class", 1, 2)]


def test_async_method_is_a_method():
    text = "class A:\n    async def run(self):\n        pass\n"
    assert summary(chunk_python("a.py", text))[1] == ("A.run", "method", 2, 3)


def test_chunks_follow_file_order():
    text = CALCULATOR + "\n\ndef helper():\n    pass\n"
    names = [c["name"] for c in chunk_python("a.py", text)]
    assert names == ["Calculator", "Calculator.add", "Calculator.subtract", "helper"]


# --- decorators ---


def test_decorator_is_part_of_the_function_chunk():
    text = "@staticmethod\ndef square(x):\n    return x * x\n"
    [chunk] = chunk_python("a.py", text)
    assert (chunk["start_line"], chunk["end_line"]) == (1, 3)
    assert chunk["text"].startswith("@staticmethod")


def test_chunk_starts_at_the_topmost_decorator():
    text = "@one\n@two(\n    1,\n)\ndef f():\n    pass\n"
    [chunk] = chunk_python("a.py", text)
    assert chunk["start_line"] == 1


def test_decorated_class_and_method():
    text = "@dataclass\nclass Point:\n    @property\n    def x(self):\n        return 1\n"
    assert summary(chunk_python("a.py", text)) == [
        ("Point", "class", 1, 5),
        ("Point.x", "method", 3, 5),
    ]


# --- the module header ---

MAIN = '''import sys
from calculator.cli import run

VERSION = "1.0"

def main():
    run(sys.argv)

if __name__ == "__main__":
    main()
'''


def test_module_header_is_first_and_holds_top_level_code():
    header = chunk_python("main.py", MAIN)[0]
    assert (header["name"], header["kind"]) == ("<module>", "module")
    assert (header["start_line"], header["end_line"]) == (1, 10)
    assert "import sys" in header["text"]
    assert 'VERSION = "1.0"' in header["text"]
    assert 'if __name__ == "__main__":' in header["text"]
    assert "def main" not in header["text"]


def test_no_module_header_when_only_a_function():
    assert [c["kind"] for c in chunk_python("a.py", "def f():\n    pass\n")] == ["function"]


def test_module_header_of_a_single_import():
    [header] = chunk_python("a.py", "import os\n")
    assert (header["name"], header["start_line"], header["end_line"]) == ("<module>", 1, 1)


def test_decorator_and_method_lines_stay_out_of_the_module_header():
    text = "import os\n\n@deco\ndef f():\n    pass\n\nclass A:\n    def m(self):\n        pass\n"
    header = chunk_python("a.py", text)[0]
    assert header["text"] == "import os"


# --- regex fallback ---

SHELL = '''#!/bin/sh
set -e
function build() {
  make
}
function clean() {
  rm -rf out
}
'''


def test_regex_cuts_at_definition_lines():
    assert summary(chunk_by_regex("run.sh", SHELL)) == [
        ("<module>", "module", 1, 2),
        ("build", "definition", 3, 5),
        ("clean", "definition", 6, 8),
    ]


def test_regex_without_module_part():
    chunks = chunk_by_regex("a.txt", "def a():\n    pass\ndef b():\n    pass")
    assert summary(chunks) == [("a", "definition", 1, 2), ("b", "definition", 3, 4)]


def test_regex_without_definitions_is_one_module_chunk():
    assert summary(chunk_by_regex("a.txt", "hello\nworld")) == [("<module>", "module", 1, 2)]


def test_regex_on_empty_or_blank_text():
    assert chunk_by_regex("a.txt", "") == []
    assert chunk_by_regex("a.txt", "\n  \n") == []


def test_regex_recognises_indented_defs_and_classes():
    chunks = chunk_by_regex("a.py", "class Foo:\n    def run(self):\n        pass\n")
    assert [c["name"] for c in chunks] == ["Foo", "run"]


def test_regex_leaves_out_blank_lines_at_the_edges_of_a_chunk():
    chunks = chunk_by_regex("a.txt", "def a():\n    pass\n\n\ndef b():\n    pass\n")
    assert summary(chunks) == [("a", "definition", 1, 2), ("b", "definition", 5, 6)]


# --- Python that does not parse ---


def test_broken_python_falls_back_to_regex():
    chunks = chunk_python("a.py", "def add(a, b:\n    return a + b\n")
    assert [(c["name"], c["kind"]) for c in chunks] == [("add", "definition")]


def test_broken_class_is_still_indexed():
    chunks = chunk_python("a.py", "class Broken\n    def run(self):\n        pass\n")
    assert [(c["name"], c["kind"]) for c in chunks] == [("Broken", "definition"), ("run", "definition")]


def test_null_byte_does_not_crash():
    assert chunk_python("a.py", "x = 1\x00\n")


def test_valid_python_does_not_use_the_fallback():
    assert chunk_python("a.py", "def f():\n    pass\n")[0]["kind"] == "function"


# --- YAML ---

YAML = '''# IoC settings
validate: python -m py_compile {files} && python -m pytest -q
services:
  web:
    image: nginx
ports:
  - 8000
'''


def test_yaml_one_chunk_per_top_level_key():
    assert summary(chunk_yaml("a.yml", YAML)) == [
        ("validate", "yaml_key", 2, 2),
        ("services", "yaml_key", 3, 5),
        ("ports", "yaml_key", 6, 7),
    ]


def test_yaml_nested_key_with_the_same_name_is_not_a_chunk():
    assert summary(chunk_yaml("a.yml", "a:\n  a: 1\n")) == [("a", "yaml_key", 1, 2)]


def test_yaml_list_is_one_module_chunk():
    assert summary(chunk_yaml("a.yml", "- a\n- b\n")) == [("<module>", "module", 1, 2)]


def test_yaml_empty_and_comment_only():
    assert chunk_yaml("a.yml", "") == []
    assert chunk_yaml("a.yml", "# just a comment\n") == [
        make_chunk("a.yml", 1, 1, "<module>", "module", "# just a comment")
    ]


def test_yaml_real_config(real_target):
    with open(os.path.join(real_target, "ioc.config.yml")) as f:
        [chunk] = chunk_yaml("ioc.config.yml", f.read())
    assert chunk["name"] == "validate"
    assert "pytest" in chunk["text"]


# --- Markdown ---

MARKDOWN = '''Intro text.
# Calculator
A tiny calculator.
## Usage
```sh
# run it
python main.py 2 + 3
```
'''


def test_markdown_one_chunk_per_heading_and_code_fences_are_not_headings():
    assert summary(chunk_markdown("README.md", MARKDOWN)) == [
        ("<module>", "module", 1, 1),
        ("Calculator", "heading", 2, 3),
        ("Usage", "heading", 4, 8),
    ]


def test_markdown_adjacent_headings():
    chunks = chunk_markdown("a.md", "# A\ntext\n# B\nmore")
    assert summary(chunks) == [("A", "heading", 1, 2), ("B", "heading", 3, 4)]


def test_markdown_plain_text_and_empty():
    assert summary(chunk_markdown("a.md", "plain text only")) == [("<module>", "module", 1, 1)]
    assert chunk_markdown("a.md", "") == []


def test_markdown_deep_heading_name():
    assert chunk_markdown("a.md", "### Deep heading")[0]["name"] == "Deep heading"


def test_markdown_real_readme(real_target):
    with open(os.path.join(real_target, "README.md")) as f:
        chunks = chunk_markdown("README.md", f.read())
    assert [c for c in chunks if c["kind"] == "heading"]


# --- chunk_file picks the chunker ---


def first_kind(path, text):
    return chunk_file(path, text)[0]["kind"]


def test_chunk_file_chooses_by_extension():
    assert first_kind("a.py", "def f():\n    pass\n") == "function"
    assert first_kind("a.yml", "a: 1\n") == "yaml_key"
    assert first_kind("a.YAML", "a: 1\n") == "yaml_key"
    assert first_kind("README.MD", "# Title\n") == "heading"
    assert first_kind("build.sh", "function build() {\n}\n") == "definition"
    assert first_kind("Makefile", "build:\n\tmake\n") == "module"


def test_every_file_of_the_real_target_can_be_chunked(real_target):
    for folder, _, names in os.walk(real_target):
        if "__pycache__" in folder or ".pytest_cache" in folder:
            continue
        for name in names:
            path = os.path.join(folder, name)
            with open(path) as f:
                chunk_file(os.path.relpath(path, real_target), f.read())


def test_real_calculator_has_four_methods(real_target):
    with open(os.path.join(real_target, "calculator", "core.py")) as f:
        chunks = chunk_file("calculator/core.py", f.read())
    methods = [c["name"] for c in chunks if c["kind"] == "method"]
    assert methods == ["Calculator.add", "Calculator.subtract", "Calculator.multiply", "Calculator.divide"]
