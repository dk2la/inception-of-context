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
