import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from p1 import index
from p3 import loop


@pytest.fixture
def target(temp_index):
    """The empty temporary Target Project, as a Path."""
    return Path(temp_index)


# --- load_validation_command ---


def test_load_validation_command_returns_the_validate_line(target):
    (target / "ioc.config.yml").write_text("validate: echo ok\n")
    assert loop.load_validation_command() == "echo ok"


def test_load_validation_command_reads_the_real_target_project(monkeypatch, real_target):
    monkeypatch.setattr(index, "TARGET_DIR", real_target)
    command = loop.load_validation_command()
    assert "pytest" in command and "{files}" in command


@pytest.mark.parametrize("config_text", ["other: 1\n", "", "validate: ''\n", "validate: 5\n", "- a list\n"])
def test_load_validation_command_rejects_a_config_without_a_validate_string(target, config_text):
    (target / "ioc.config.yml").write_text(config_text)
    with pytest.raises(ValueError, match="'validate' command"):
        loop.load_validation_command()


def test_load_validation_command_without_a_config_file_raises_file_not_found(target):
    with pytest.raises(FileNotFoundError):
        loop.load_validation_command()


# --- run_validation ---

COMPILE_THEN_PRINT = "validate: python -m py_compile {files} && python -c \"print('tests ran')\"\n"


def test_run_validation_passes_when_the_command_succeeds(target):
    (target / "ioc.config.yml").write_text(COMPILE_THEN_PRINT)
    (target / "good.py").write_text("x = 1\n")
    ok, log = loop.run_validation(["good.py"])
    assert ok is True
    assert "tests ran" in log


def test_run_validation_runs_python_with_the_interpreter_that_runs_the_server(target, monkeypatch):
    monkeypatch.setenv("PATH", str(target))  # a PATH with no python in it
    (target / "ioc.config.yml").write_text("validate: python -c \"import sys; print(sys.prefix)\"\n")
    ok, log = loop.run_validation([])
    assert ok is True
    assert log.strip() == sys.prefix


def test_run_validation_fails_on_a_syntax_error_and_does_not_run_the_tests(target):
    (target / "ioc.config.yml").write_text(COMPILE_THEN_PRINT)
    (target / "bad.py").write_text("def broken(:\n")
    ok, log = loop.run_validation(["bad.py"])
    assert ok is False
    assert "SyntaxError" in log
    assert "tests ran" not in log


def test_run_validation_with_no_python_files_still_runs_the_tests(target):
    (target / "ioc.config.yml").write_text(COMPILE_THEN_PRINT)
    ok, log = loop.run_validation(["README.md"])
    assert ok is True
    assert "tests ran" in log
    assert "usage" not in log.lower()


def test_run_validation_ignores_a_deleted_python_file(target):
    (target / "ioc.config.yml").write_text(COMPILE_THEN_PRINT)
    ok, log = loop.run_validation(["deleted.py"])
    assert ok is True


def test_run_validation_fails_when_the_command_exits_with_an_error_code(target):
    (target / "ioc.config.yml").write_text("validate: exit 3\n")
    ok, log = loop.run_validation([])
    assert ok is False


def test_run_validation_quotes_file_names_with_spaces(target):
    (target / "ioc.config.yml").write_text(COMPILE_THEN_PRINT)
    (target / "my file.py").write_text("x = 1\n")
    ok, log = loop.run_validation(["my file.py"])
    assert ok is True


def test_run_validation_runs_in_the_target_project_and_captures_errors_too(target):
    (target / "ioc.config.yml").write_text("validate: pwd && echo oops >&2 && exit 1\n")
    ok, log = loop.run_validation([])
    assert ok is False
    assert str(target.resolve()) in log
    assert "oops" in log


def test_run_validation_stops_a_command_that_takes_too_long(target, monkeypatch):
    monkeypatch.setattr(loop, "VALIDATION_TIMEOUT", 1)
    (target / "ioc.config.yml").write_text("validate: sleep 30\n")
    start = time.time()
    result = loop.run_validation([])
    assert result == (False, "validation timed out after 1 seconds")
    assert time.time() - start < 5


def test_run_validation_timeout_kills_the_children_of_the_shell_too(target, monkeypatch):
    monkeypatch.setattr(loop, "VALIDATION_TIMEOUT", 1)
    # the subshell is a child of the shell: killing only the shell would let it create the file
    (target / "ioc.config.yml").write_text("validate: (sleep 2 && touch finished.txt); echo done\n")
    ok, log = loop.run_validation([])
    assert ok is False
    time.sleep(2.5)
    assert not (target / "finished.txt").exists()


def test_run_validation_returns_the_output_of_a_fast_command(target):
    (target / "ioc.config.yml").write_text("validate: echo ok\n")
    assert loop.run_validation([]) == (True, "ok\n")


# --- take_snapshot ---


def test_take_snapshot_stores_the_bytes_of_a_file(target):
    (target / "a.py").write_bytes(b"x = 1\n")
    assert loop.take_snapshot(["a.py"]) == {"a.py": b"x = 1\n"}


def test_take_snapshot_stores_none_for_a_file_that_does_not_exist(target):
    assert loop.take_snapshot(["new.py"]) == {"new.py": None}


def test_take_snapshot_keys_files_in_subfolders_by_their_relative_path(target):
    (target / "pkg").mkdir()
    (target / "pkg" / "b.py").write_bytes(b"y = 2\n")
    assert loop.take_snapshot(["pkg/b.py"]) == {"pkg/b.py": b"y = 2\n"}


def test_take_snapshot_keeps_windows_line_endings(target):
    (target / "a.py").write_bytes(b"x = 1\r\n")
    assert loop.take_snapshot(["a.py"]) == {"a.py": b"x = 1\r\n"}


def test_take_snapshot_of_no_paths_is_empty(target):
    assert loop.take_snapshot([]) == {}


# --- restore_snapshot (Rollback) ---


def read_tree(root):
    """Every file under root as {relative path: bytes}, to compare whole folders byte for byte."""
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_restore_snapshot_puts_back_a_modified_file(target):
    (target / "a.py").write_bytes(b"x = 1\n")
    snapshot = loop.take_snapshot(["a.py"])
    (target / "a.py").write_bytes(b"x = 2\n")
    loop.restore_snapshot(snapshot)
    assert (target / "a.py").read_bytes() == b"x = 1\n"


def test_restore_snapshot_deletes_a_file_the_patch_created(target):
    snapshot = loop.take_snapshot(["new.py"])
    (target / "new.py").write_bytes(b"x = 1\n")
    loop.restore_snapshot(snapshot)
    assert not (target / "new.py").exists()


def test_restore_snapshot_puts_back_a_deleted_file_and_its_folder(target):
    (target / "pkg").mkdir()
    (target / "pkg" / "b.py").write_bytes(b"y = 2\n")
    snapshot = loop.take_snapshot(["pkg/b.py"])
    (target / "pkg" / "b.py").unlink()
    (target / "pkg").rmdir()
    loop.restore_snapshot(snapshot)
    assert (target / "pkg" / "b.py").read_bytes() == b"y = 2\n"


def test_restore_snapshot_restores_bytes_exactly(target):
    original = "café = 1\r\nprint(café)\r\n".encode("utf-8")
    (target / "a.py").write_bytes(original)
    snapshot = loop.take_snapshot(["a.py"])
    (target / "a.py").write_bytes(b"x = 2\n")
    loop.restore_snapshot(snapshot)
    assert (target / "a.py").read_bytes() == original


def test_restore_snapshot_twice_is_safe(target):
    (target / "a.py").write_bytes(b"x = 1\n")
    snapshot = loop.take_snapshot(["a.py", "new.py"])
    (target / "a.py").write_bytes(b"x = 2\n")
    (target / "new.py").write_bytes(b"y = 1\n")
    loop.restore_snapshot(snapshot)
    loop.restore_snapshot(snapshot)
    assert (target / "a.py").read_bytes() == b"x = 1\n"
    assert not (target / "new.py").exists()


def test_restore_snapshot_leaves_the_whole_target_project_byte_for_byte_as_it_was(target, real_target):
    shutil.copytree(real_target, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    before = read_tree(target)
    snapshot = loop.take_snapshot(["calculator/core.py", "calculator/cli.py", "calculator/power.py"])
    (target / "calculator" / "core.py").write_text("changed\n")
    (target / "calculator" / "cli.py").unlink()
    (target / "calculator" / "power.py").write_text("def power(a, b): return a ** b\n")
    loop.restore_snapshot(snapshot)
    assert read_tree(target) == before


# --- apply_patch ---


def make_patch(*files):
    """A Patch from (path, op, content) tuples."""
    return {"summary": "test", "files": [{"path": p, "op": op, "content": c} for p, op, c in files]}


def test_apply_patch_modifies_a_file(target):
    (target / "a.py").write_text("x = 1\n")
    loop.apply_patch(make_patch(("a.py", "modify", "x = 2\n")))
    assert (target / "a.py").read_text() == "x = 2\n"


def test_apply_patch_creates_a_file_in_a_new_folder(target):
    loop.apply_patch(make_patch(("pkg/new.py", "create", "y = 1\n")))
    assert (target / "pkg" / "new.py").read_text() == "y = 1\n"


def test_apply_patch_deletes_a_file(target):
    (target / "old.md").write_text("notes\n")
    loop.apply_patch(make_patch(("old.md", "delete", "")))
    assert not (target / "old.md").exists()


def test_apply_patch_leaves_no_temporary_files(target):
    (target / "a.py").write_text("x = 1\n")
    loop.apply_patch(make_patch(("a.py", "modify", "x = 2\n"), ("pkg/new.py", "create", "y = 1\n")))
    assert list(target.glob("**/*.ioc.tmp")) == []


def test_apply_patch_returns_the_touched_paths_in_patch_order(target):
    (target / "a.py").write_text("x = 1\n")
    (target / "old.md").write_text("notes\n")
    patch = make_patch(("pkg/new.py", "create", "y = 1\n"), ("old.md", "delete", ""), ("a.py", "modify", "x = 2\n"))
    assert loop.apply_patch(patch) == ["pkg/new.py", "old.md", "a.py"]


def test_apply_patch_that_fails_while_preparing_leaves_the_real_files_untouched(target):
    (target / "a.py").write_text("x = 1\n")
    patch = make_patch(("a.py", "modify", "x = 2\n"), ("a.py/inner.py", "create", "y = 1\n"))  # a.py is a file
    with pytest.raises(OSError):
        loop.apply_patch(patch)
    assert (target / "a.py").read_text() == "x = 1\n"
    assert list(target.glob("**/*.ioc.tmp")) == []


def test_apply_patch_then_rollback_leaves_the_whole_target_project_byte_for_byte_as_it_was(target, real_target):
    shutil.copytree(real_target, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    before = read_tree(target)
    patch = make_patch(
        ("calculator/core.py", "modify", "changed\n"),
        ("calculator/cli.py", "delete", ""),
        ("calculator/power.py", "create", "def power(a, b): return a ** b\n"),
    )
    snapshot = loop.take_snapshot([f["path"] for f in patch["files"]])
    loop.apply_patch(patch)
    loop.restore_snapshot(snapshot)
    assert read_tree(target) == before


# --- validation after a Rollback must run the restored code, not a stale .pyc ---

ADD_PLUS = "def add(a, b):\n    return a + b\n"
ADD_MINUS = "def add(a, b):\n    return a - b\n"  # same size as ADD_PLUS
TEST_ADD = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def make_calc_project(target):
    (target / "ioc.config.yml").write_text("validate: python -m py_compile {files} && python -m pytest -q\n")
    (target / "calc.py").write_text(ADD_PLUS)
    (target / "test_calc.py").write_text(TEST_ADD)


def same_second(path):
    """Give the file a fixed modification time, as if it was written in the same second as before."""
    os.utime(path, (1_700_000_000, 1_700_000_000))


def test_validation_after_a_rollback_runs_the_restored_code_not_a_stale_pyc(target):
    make_calc_project(target)
    snapshot = loop.take_snapshot(["calc.py"])
    loop.apply_patch(make_patch(("calc.py", "modify", ADD_MINUS)))
    same_second(target / "calc.py")
    assert loop.run_validation(["calc.py"])[0] is False
    loop.restore_snapshot(snapshot)
    same_second(target / "calc.py")
    assert loop.run_validation([])[0] is True  # no .py file to recompile: it must not run an old .pyc


def test_validation_leaves_no_pycache_in_the_target_project(target):
    make_calc_project(target)
    ok, log = loop.run_validation(["calc.py"])
    assert ok is True
    assert list(target.glob("**/__pycache__")) == []


# --- parse_patch ---

GOOD_PATCH = {"summary": "Add power", "files": [{"path": "a.py", "op": "modify", "content": "x"}]}


def test_parse_patch_accepts_a_well_formed_patch():
    assert loop.parse_patch(json.dumps(GOOD_PATCH)) == (GOOD_PATCH, None)


def test_parse_patch_drops_keys_the_model_invented():
    patch = dict(GOOD_PATCH, thoughts="hmm")
    patch["files"] = [dict(GOOD_PATCH["files"][0], extra=1)]
    assert loop.parse_patch(json.dumps(patch)) == (GOOD_PATCH, None)


def test_parse_patch_fills_in_a_missing_summary():
    patch, reason = loop.parse_patch(json.dumps({"files": GOOD_PATCH["files"]}))
    assert reason is None
    assert patch["summary"] == ""


def test_parse_patch_fills_in_a_missing_content_of_a_delete():
    text = json.dumps({"files": [{"path": "old.md", "op": "delete"}]})
    patch, reason = loop.parse_patch(text)
    assert reason is None
    assert patch["files"] == [{"path": "old.md", "op": "delete", "content": ""}]


@pytest.mark.parametrize("text, expected_reason", [
    ("Sure! Here is the code", "the model did not return valid JSON: Expecting value"),
    ("[1, 2]", "the Patch must be a JSON object"),
    ('{"summary": "x"}', "the Patch has no files"),
    ('{"files": []}', "the Patch has no files"),
    ('{"files": "a.py"}', "the Patch has no files"),
])
def test_parse_patch_gives_a_reason_when_the_top_level_is_wrong(text, expected_reason):
    patch, reason = loop.parse_patch(text)
    assert patch is None
    assert reason.startswith(expected_reason)


GOOD_FILE = {"path": "a.py", "op": "modify", "content": "x"}


@pytest.mark.parametrize("bad_file, expected_reason", [
    ("just a string", "file 2: must be a JSON object"),
    ({"op": "modify", "content": "x"}, "file 2: path must be a non-empty string"),
    ({"path": "", "op": "modify", "content": "x"}, "file 2: path must be a non-empty string"),
    ({"path": 7, "op": "modify", "content": "x"}, "file 2: path must be a non-empty string"),
    ({"path": "b.py", "op": "update", "content": "x"}, "file 2: op must be create, modify or delete, got 'update'"),
    ({"path": "b.py", "content": "x"}, "file 2: op must be create, modify or delete, got None"),
    ({"path": "b.py", "op": "modify", "content": 42}, "file 2: content must be a string"),
    ({"path": "b.py", "op": "create"}, "file 2: content must be a string"),
])
def test_parse_patch_names_the_file_entry_that_is_wrong(bad_file, expected_reason):
    patch, reason = loop.parse_patch(json.dumps({"summary": "x", "files": [GOOD_FILE, bad_file]}))
    assert patch is None
    assert reason == expected_reason
