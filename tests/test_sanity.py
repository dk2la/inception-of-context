import os
import shutil

import pytest

from p3 import sanity
from p3.sanity import check_patch


# --- helpers ---

def listing(folder):
    """Every file under folder, with its bytes, so a test can prove nothing was written."""
    found = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                found[path] = f.read()
    return found


@pytest.fixture
def project(tmp_path, real_target):
    """A temporary copy of the real Target Project, inside a folder that holds nothing else."""
    folder = tmp_path / "work" / "target"
    shutil.copytree(real_target, folder, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return str(folder)


@pytest.fixture
def run(project):
    """run(patch) -> the Sanity Check reason or None, and proves that nothing under work/ was written."""
    def run(patch):
        work = os.path.dirname(project)
        before = listing(work)
        reason = check_patch(patch, project)
        assert listing(work) == before
        return reason
    return run


def patch_of(*files):
    return {"summary": "test", "files": list(files)}


def modify(path, content="x = 1\n"):
    return {"path": path, "op": "modify", "content": content}


def create(path, content="x = 1\n"):
    return {"path": path, "op": "create", "content": content}


def delete(path):
    return {"path": path, "op": "delete"}


# --- the runner and outside_target (#92) ---

def test_a_normal_patch_is_allowed(run):
    assert run(patch_of(create("calculator/power.py", "def power(a, b):\n    return a ** b\n"))) is None


def test_the_runner_returns_the_first_reason_and_stops_there(run, monkeypatch):
    calls = []

    def rule(answer):
        def the_rule(patch, target_dir):
            calls.append(answer)
            return answer
        return the_rule

    monkeypatch.setattr(sanity, "RULES", [rule(None), rule("second"), rule("third")])
    assert run(patch_of(create("a.py"))) == "second"
    assert calls == [None, "second"]


@pytest.mark.parametrize("path", [
    "/etc/passwd",              # absolute
    "../x.py",                  # climbs out
    "calculator/../../x.py",    # starts inside, climbs out
    "./../x.py",                # looks inside, resolves outside
    "..\\x.py",                 # Windows-style separators
    "calculator\\..\\..\\x.py",
    "\\etc\\passwd",            # Windows-style absolute
    "..",
])
def test_a_path_outside_the_target_project_is_refused_and_named(run, path):
    assert path in run(patch_of(create(path)))


def test_one_bad_path_among_good_ones_is_enough(run):
    reason = run(patch_of(create("a.py"), create("../x.py")))
    assert "../x.py" in reason


def test_a_path_that_only_contains_dots_in_a_name_is_allowed(run):
    assert run(patch_of(create("calculator/v1..2.py"), create("...py"))) is None


# --- touches_config (#93) ---

@pytest.mark.parametrize("entry", [
    modify("ioc.config.yml", "validate: 'true'\n"),
    delete("ioc.config.yml"),
    create("./ioc.config.yml"),
    modify("calculator/../ioc.config.yml"),
    modify(".\\ioc.config.yml"),
])
def test_the_config_file_is_never_touched_in_any_spelling(project, entry):
    # Called directly, because 'calculator/../' would be refused earlier by outside_target.
    reason = sanity.touches_config(patch_of(entry), project)
    assert "ioc.config.yml" in reason and "Validation Command" in reason


def test_a_patch_touching_the_config_among_other_files_is_refused(run):
    reason = run(patch_of(modify("calculator/core.py", "x = 1\n" * 100), modify("ioc.config.yml")))
    assert "ioc.config.yml" in reason


def test_the_config_is_refused_by_the_runner(run):
    assert "Validation Command" in run(patch_of(modify("./ioc.config.yml")))
    assert "ioc.config.yml" in run(patch_of(modify("calculator/../ioc.config.yml")))


def test_files_with_similar_names_are_allowed(run):
    assert run(patch_of(create("docs/ioc.config.yml.md"), create("sub/ioc.config.yml"))) is None


# --- too_many_files (#94) ---

def files_named(count):
    return [create(f"new{i}.py") for i in range(count)]


@pytest.mark.parametrize("count", [1, 3])
def test_up_to_three_files_are_allowed(run, count):
    assert run(patch_of(*files_named(count))) is None


def test_four_files_are_refused_with_the_count_and_the_limit(run):
    reason = run(patch_of(*files_named(4)))
    assert "4" in reason and "3" in reason


def test_every_operation_counts_towards_the_limit(run):
    patch = patch_of(create("new.py"), modify("calculator/core.py", "x = 1\n" * 100),
                     delete("calculator/cli.py"), delete("main.py"))
    assert "4" in run(patch)


def test_too_many_files_can_be_called_directly(project):
    assert isinstance(sanity.too_many_files(patch_of(*files_named(4)), project), str)


def test_the_path_rule_runs_before_the_count(run):
    reason = run(patch_of(*files_named(3), create("../x.py")))
    assert "path outside target project" in reason


# --- creates_existing (#95) ---

def write(project, name, text):
    """Put a file in the temporary Target Project."""
    path = os.path.join(project, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def test_create_of_a_missing_file_is_allowed(run):
    assert run(patch_of(create("new.py"), create("sub/new.py"))) is None


def test_create_of_an_existing_file_is_refused_and_names_it(project, run):
    write(project, "a.py", "x = 1\n")
    reason = run(patch_of(create("a.py")))
    assert "a.py" in reason and "modify" in reason


def test_create_of_an_existing_file_in_a_folder_is_refused(run):
    assert "calculator/core.py" in run(patch_of(create("calculator/core.py")))


def test_create_of_an_existing_file_is_refused_even_spelled_with_a_dot(run):
    assert "main.py" in run(patch_of(create("./main.py")))


def test_modify_and_delete_of_an_existing_file_are_ignored_by_this_rule(project):
    write(project, "a.py", "x = 1\n")
    assert sanity.creates_existing(patch_of(modify("a.py"), delete("a.py")), project) is None
