import pytest

from ioc_index.walker import FileFilter
from ioc_patch.sanity import check_patch, stub_functions
from ioc_patch.schema import PatchFormatError, parse_patch


def patch(*files, summary="s"):
    return parse_patch({"summary": summary, "files": [dict(zip(("path", "op", "content"), f)) for f in files]})


def errors(target, *files):
    return check_patch(patch(*files), target, FileFilter(target))


def test_parse_tolerates_fences_aliases_and_rejects_garbage():
    p = parse_patch('Sure!\n```json\n{"summary": "x", "files": [{"path": "./a.py", "op": "update", "content": "x=1"}]}\n```')
    assert p.files[0].path == "a.py" and p.files[0].op == "modify"
    for bad in ["no json here", '{"files": []}', '{"files": [{"path": "a", "op": "patch"}]}', "[1,2]",
                '{"files": [{"path": "a.py", "op": "create", "content": 3}]}']:
        with pytest.raises(PatchFormatError):
            parse_patch(bad)
    assert parse_patch('{"files":[{"path":"a.py","op":"modify","content":null}]}').files[0].content == "None"


def test_good_patch_passes(target):
    src = (target / "main.py").read_text() + "\n\ndef whisper(name):\n    return greet(name).lower()\n"
    assert errors(target, ("main.py", "modify", src)) == []


def test_markers(target):
    src = (target / "main.py").read_text() + "\n<<<IOC_FILE main.py>>>\n"
    assert "marker" in errors(target, ("main.py", "modify", src))[0]
    src = "```python\n" + (target / "main.py").read_text() + "\n```\n"
    assert any("code fence" in e for e in errors(target, ("main.py", "modify", src)))


def test_create_existing_and_modify_missing(target):
    assert "already exists" in errors(target, ("main.py", "create", "x = 1\n"))[0]
    assert "does not exist" in errors(target, ("nope.py", "modify", "x = 1\n"))[0]
    assert "does not exist" in errors(target, ("nope.py", "delete", None))[0]


@pytest.mark.parametrize("empty", ["", "None", "null", "  \n"])
def test_emptying_a_file(target, empty):
    assert "non-empty file" in errors(target, ("main.py", "modify", empty))[0]


def test_stubs_are_refused_but_existing_ones_tolerated(target):
    base = (target / "main.py").read_text()
    for body in ["pass", "...", "return None", "return", '"""doc"""', 'raise NotImplementedError("x")']:
        errs = errors(target, ("main.py", "modify", base + f"\n\ndef new_func(x):\n    {body}\n"))
        assert any("stub" in e and "new_func" in e for e in errs), body
    errs = errors(target, ("main.py", "modify", base + "\n\nclass K:\n    def m(self):\n        pass\n"))
    assert any("K.m" in e for e in errs)
    (target / "abstract.py").write_text("class Base:\n    def run(self):\n        raise NotImplementedError\n")
    ok = "class Base:\n    def run(self):\n        raise NotImplementedError\n\n    def name(self):\n        return 'base'\n"
    assert errors(target, ("abstract.py", "modify", ok)) == []
    assert stub_functions("def f(:\n") is None


def test_shrinking_more_than_60_percent(target):
    src = (target / "notes/service.py").read_text()
    assert "shrink" in errors(target, ("notes/service.py", "modify", src[: int(len(src) * 0.3)]))[0]
    assert not any("shrink" in e for e in errors(target, ("notes/service.py", "modify", src[: int(len(src) * 0.7)])))


def test_more_than_three_files(target):
    files = [(f"new{i}.py", "create", f"X{i} = {i}\n") for i in range(4)]
    assert "at most 3" in errors(target, *files)[0]


@pytest.mark.parametrize("path", ["../evil.py", "/etc/passwd", "notes/../../evil.py", ".git/config", "node_modules/x.js", "a.py.ioc.tmp"])
def test_paths_outside_or_excluded(target, path):
    assert errors(target, (path, "create", "x = 1\n"))


def test_unchanged_modify(target):
    assert "unchanged" in errors(target, ("main.py", "modify", (target / "main.py").read_text()))[0]
