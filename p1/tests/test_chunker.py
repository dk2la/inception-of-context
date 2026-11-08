from ioc_index.chunker import chunk_file

SRC = '''"""doc"""
import os


@decorator
def top(a):
    def inner():
        return 1
    return inner()


class Foo(Base):
    """Foo doc."""
    x = 1

    def bar(self):
        return 2

    @property
    async def baz(self):
        return 3

    class Inner:
        def deep(self):
            pass


if __name__ == "__main__":
    top(1)
'''


def test_python_chunks_follow_logical_structure():
    chunks = chunk_file("m.py", SRC)
    got = [(c.kind, c.symbol, c.start_line, c.end_line) for c in chunks]
    assert got == [
        ("module", "<module>", 1, 2),
        ("function", "top", 5, 9),               # decorator included, nested def stays inside
        ("class", "Foo", 12, 14),
        ("method", "Foo.bar", 16, 17),
        ("method", "Foo.baz", 19, 21),           # decorator + async
        ("class", "Foo.Inner", 23, 23),
        ("method", "Foo.Inner.deep", 24, 25),
        ("module", "<module>", 28, 29),          # code after the last definition
    ]


def test_chunks_partition_file_without_overlap():
    chunks = chunk_file("m.py", SRC)
    for a, b in zip(chunks, chunks[1:]):
        assert a.end_line < b.start_line


def test_broken_python_falls_back_to_regex():
    src = "def ok():\n    return 1\n\ndef broken(:\n    pass\n\nclass K:\n    def m(self):\n        pass\n"
    got = [(c.kind, c.symbol, c.start_line) for c in chunk_file("x.py", src)]
    assert got == [("function", "ok", 1), ("function", "broken", 4), ("class", "K", 7), ("method", "K.m", 8)]


def test_yaml_blocks_and_markdown_sections():
    y = "# comment\nvalidate:\n  command: x\n\nother:\n  a: 1\n"
    assert [(c.symbol, c.start_line) for c in chunk_file("c.yml", y)] == [("validate", 1), ("other", 5)]
    md = "intro\n\n# Title\ntext\n```\n# not a heading\n```\n## Sub\nmore\n"
    assert [c.symbol for c in chunk_file("r.md", md)] == ["<intro>", "Title", "Sub"]


def test_js_regex_chunks():
    js = "import x from 'y';\n\nexport function a() {\n  return 1;\n}\n\nconst b = async (x) => {\n  return x;\n};\n\nclass C {\n}\n"
    assert [c.symbol for c in chunk_file("f.js", js)] == ["<module>", "a", "b", "C"]


def test_empty_file_has_no_chunks():
    assert chunk_file("e.py", "\n\n") == []
