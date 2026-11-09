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
