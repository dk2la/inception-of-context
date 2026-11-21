"""Sanity Checks: hard rules that refuse a Patch before anything touches the disk.

Each rule is a method (patch, target_dir) of SanityService that returns a reason string, or None if the Patch is fine.
A Patch looks like {"summary": ..., "files": [{"path": ..., "op": "create|modify|delete", "content": ...}]}.
"""
import ast
import os

from p1.config.settings import settings

MARKER = "=== FILE:"  # the line that starts each file in the Patch prompt; it must never reach a file
# Added to every refusal about an existing test file. The reason goes back to the model for its next Attempt,
# so it says what to do instead: a small model that is only told "no" sends the same mistake again.
NEW_TEST_FILE = ". Leave {path} exactly as it is and put new tests in a NEW file such as tests/test_<feature>.py"


class SanityService:
    def __init__(self, settings):
        # debug: settings.VALIDATION_CONFIG == "ioc.config.yml"
        # settings.MAX_FILES == 3, settings.MAX_SHRINK == 60
        # self.rules is 11 bound methods, in the order below. check_patch walks them.
        self.settings = settings
        # outside_target must stay first: the rules after it read files from disk and trust the paths are inside.
        # Then the cheap rules that only look at the Patch, then the ones that read files (empties_file before
        # shrinks_too_much, so "replaced by nothing" gets its more specific reason), then the one that parses code.
        self.rules = [self.outside_target, self.touches_config, self.targets_folder, self.too_many_files,
                      self.has_marker, self.creates_existing, self.changes_nothing, self.weakens_tests,
                      self.empties_file, self.shrinks_too_much, self.stub_function]

    def outside_target(self, patch, target_dir):
        """Refuse absolute paths and paths with a '..' part (a backslash counts as a separator)."""
        # debug: target_dir == "/workspace"
        # patch["files"][0]["path"] == "calculator/core.py" -> return == None
        # path "../etc/passwd" -> return == "path outside target project: ../etc/passwd"
        # path "/tmp/x.py" -> return == "path outside target project: /tmp/x.py"
        for entry in patch["files"]:
            path = entry["path"].replace("\\", "/")
            if os.path.isabs(path) or ".." in path.split("/"):
                return f"path outside target project: {entry['path']}"
        return None

    def touches_config(self, patch, target_dir):
        """Refuse any change to ioc.config.yml, so the model cannot weaken the Validation Command."""
        # debug: path "calculator/core.py" -> return == None
        # path "ioc.config.yml" or "IOC.config.yml" ->
        # return == "the Patch may not change ioc.config.yml (it holds the Validation Command)"
        for entry in patch["files"]:
            # lower(): on a case-insensitive disk (a macOS bind mount) IOC.config.yml is the same file
            if os.path.normpath(entry["path"].replace("\\", "/")).lower() == self.settings.VALIDATION_CONFIG.lower():
                return "the Patch may not change ioc.config.yml (it holds the Validation Command)"
        return None

    def targets_folder(self, patch, target_dir):
        """Refuse a path that is a folder: a Patch is made of files."""
        # debug: target_dir == "/workspace"
        # path "calculator/core.py" -> return == None
        # path "calculator" (the package folder) -> return == "calculator is a folder, not a file"
        for entry in patch["files"]:
            if os.path.isdir(os.path.join(target_dir, entry["path"])):
                return f"{entry['path']} is a folder, not a file"
        return None

    def too_many_files(self, patch, target_dir):
        """Refuse a Patch that touches more than self.settings.MAX_FILES files (create, modify and delete all count)."""
        # debug: one file, calculator/core.py -> count == 1, return == None
        # four files -> return == "patch touches 4 files, the limit is 3"
        count = len(patch["files"])
        if count > self.settings.MAX_FILES:
            return f"patch touches {count} files, the limit is {self.settings.MAX_FILES}"
        return None

    def has_marker(self, patch, target_dir):
        """Refuse content with the prompt's file marker in it: the model copied its input."""
        # debug: content is the source of calculator/core.py -> return == None
        # content contains the line "=== FILE: calculator/core.py ===" ->
        # return == "retrieval marker '=== FILE:' found in calculator/core.py"
        for entry in patch["files"]:
            if MARKER in (entry.get("content") or ""):
                return f"retrieval marker '{MARKER}' found in {entry['path']}"
        return None

    def creates_existing(self, patch, target_dir):
        """Refuse a 'create' of a file that is already there: the model has a wrong picture of the project."""
        # debug: op "modify", path "calculator/core.py" -> return == None
        # op "create", path "tests/test_power.py" (no such file yet) -> return == None
        # op "create", path "calculator/core.py" (the file is already there) ->
        # return == "create on existing file: calculator/core.py (use modify)"
        # op "create", path "tests/test_core.py" -> the same, plus NEW_TEST_FILE: "put new tests in a NEW file ..."
        for entry in patch["files"]:
            if entry.get("op") == "create" and os.path.exists(os.path.join(target_dir, entry["path"])):
                reason = f"create on existing file: {entry['path']} (use modify)"
                return reason + NEW_TEST_FILE.format(path=entry["path"]) if self.is_test_file(entry["path"]) else reason
        return None

    def old_content(self, entry, target_dir):
        """The current text of the entry's file, or "" if there is no such file."""
        # debug: target_dir == "/workspace", entry["path"] == "calculator/core.py"
        # return == "class Calculator:\n    \"\"\"A calculator that works with floats.\"\"\"\n    ..."
        # entry["path"] == "tests/test_power.py" (missing) -> return == ""
        path = os.path.join(target_dir, entry["path"])
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def changes_nothing(self, patch, target_dir):
        """Refuse a Patch whose every file already has exactly that content: it would pass the tests and do nothing."""
        # debug: core.py already has power() and the model sends core.py unchanged ->
        # return == "the patch changes nothing: calculator/core.py is already like that"
        # the same file plus one method -> return == None. Any create or delete is a change -> None
        if not patch["files"] or any(entry.get("op") != "modify" for entry in patch["files"]):
            return None
        for entry in patch["files"]:
            if (entry.get("content") or "") != self.old_content(entry, target_dir):
                return None
        paths = ", ".join(entry["path"] for entry in patch["files"])
        return f"the patch changes nothing: {paths} is already like that"

    def empties_file(self, patch, target_dir):
        """Refuse to modify a non-empty file into "", "None" or "null" (a JSON null counts as nothing too)."""
        # debug: modify calculator/core.py, content "" or "None" or "null" ->
        # return == "patch would empty calculator/core.py"
        # the same file with its full source plus a power method -> return == None
        # create of tests/test_power.py with content "" -> return == None  # only modify counts
        for entry in patch["files"]:
            if entry.get("op") != "modify" or not self.old_content(entry, target_dir).strip():
                continue
            if (entry.get("content") or "").strip() in ("", "None", "null"):
                return f"patch would empty {entry['path']}"
        return None

    def shrinks_too_much(self, patch, target_dir):
        """Refuse a modify that cuts a file by more than MAX_SHRINK percent.

        The model probably left out most of the file.
        """
        # debug: calculator/core.py is 516 bytes. content "x = 1\n" is 6 bytes.
        # shrink == 99, which is over MAX_SHRINK == 60 ->
        # return == "calculator/core.py would shrink by 99 % (limit 60 %), send the whole file"
        # content is the whole file plus one method -> return == None
        for entry in patch["files"]:
            if entry.get("op") != "modify":
                continue
            old = self.old_content(entry, target_dir)
            new = entry.get("content") or ""
            if old.strip() and len(new) < len(old) * (100 - self.settings.MAX_SHRINK) / 100:
                shrink = round(100 - 100 * len(new) / len(old))
                return (f"{entry['path']} would shrink by {shrink} % "
                        f"(limit {self.settings.MAX_SHRINK} %), send the whole file")
        return None

    def does_nothing(self, statement):
        """True for `pass`, `...` and `return None` (or a bare `return`)."""
        # debug: statement is one ast node from a function body.
        # `pass` -> True. `...` -> True. bare `return` -> True. `return None` -> True.
        # `return float(a + b)` (Calculator.add) -> False
        if isinstance(statement, ast.Pass):
            return True
        if isinstance(statement, ast.Expr):  # `...` is an expression statement holding the constant Ellipsis
            return isinstance(statement.value, ast.Constant) and statement.value.value is Ellipsis
        if isinstance(statement, ast.Return):
            value = statement.value
            return value is None or (isinstance(value, ast.Constant) and value.value is None)
        return False

    def is_stub(self, function):
        """True if the body of a function, its docstring aside, does nothing."""
        # debug: `def power(self, a, b):\n    """Return a ** b."""\n    pass`
        # the docstring is skipped, the only statement is pass -> return == True
        # Calculator.divide: `if b == 0` and `return float(a / b)` -> return == False
        body = function.body
        if ast.get_docstring(function, clean=False) is not None:
            body = body[1:]
        return all(self.does_nothing(statement) for statement in body)

    def stub_function(self, patch, target_dir):
        """Refuse a Python function whose body does nothing: it can pass the tests while the feature is missing."""
        # debug: calculator/core.py as it is, every method returns a float -> return == None
        # the same file plus `def power(...): pass` ->
        # return == "stub function power in calculator/core.py"
        # content that is not valid Python -> return == None  # py_compile reports it later
        for entry in patch["files"]:
            if entry.get("op") not in ("create", "modify") or not entry["path"].endswith(".py"):
                continue
            try:
                tree = ast.parse(entry.get("content") or "")
            except (SyntaxError, ValueError):
                continue  # py_compile in the Validation Command reports broken code better
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and self.is_stub(node):
                    return f"stub function {node.name} in {entry['path']}"
        return None

    def is_test_file(self, path):
        """A file pytest collects by default: test_*.py or *_test.py."""
        # debug: "tests/test_core.py" -> True. "tests/cli_test.py" -> True.
        # "calculator/core.py" -> False
        name = os.path.basename(path.replace("\\", "/"))
        return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))

    def tests_in(self, text):
        """{name: code} of every test function, also inside test classes. None if the text does not parse."""
        # debug: text is tests/test_core.py. keys include "test_add" and "test_divide".
        # each value is ast.dump of that function, so comments and spacing do not count.
        # text "this is not python" -> return == None
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return None
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                found[node.name] = ast.dump(node)  # the code without comments and formatting
        return found

    def weakens_tests(self, patch, target_dir):
        """Refuse a Patch that deletes a test file or removes or changes a test that exists.

        Otherwise the model could make the Validation Command pass by weakening the tests. Adding tests is fine.
        """
        # debug: calculator/core.py is not a test file, so it is skipped -> return == None
        # delete tests/test_core.py ->
        # return == "the Patch may not delete the test file tests/test_core.py"
        # modify that drops test_divide ->
        # return == "the Patch removes the test test_divide from tests/test_core.py"
        # modify that changes the body of test_add ->
        # return == "the Patch changes the test test_add in tests/test_core.py (add new tests instead)"
        # modify that only adds test_power and keeps every old test -> return == None
        for entry in patch["files"]:
            if not self.is_test_file(entry["path"]) or not os.path.isfile(os.path.join(target_dir, entry["path"])):
                continue
            if entry.get("op") == "delete":
                return (f"the Patch may not delete the test file {entry['path']}"
                        + NEW_TEST_FILE.format(path=entry["path"]))
            old = self.tests_in(self.old_content(entry, target_dir))
            new = self.tests_in(entry.get("content") or "")
            if old is None or new is None:
                continue  # py_compile in the Validation Command reports broken code better
            for name in old:
                if name not in new:
                    return (f"the Patch removes the test {name} from {entry['path']}"
                            + NEW_TEST_FILE.format(path=entry["path"]))
                if new[name] != old[name]:
                    return (f"the Patch changes the test {name} in {entry['path']} (add new tests instead)"
                            + NEW_TEST_FILE.format(path=entry["path"]))
        return None

    def check_patch(self, patch, target_dir):
        """Return the reason of the first rule that refuses the Patch, or None if it is allowed."""
        # debug: called from run_attempt, after parse_patch and before take_snapshot.
        # target_dir == "/workspace"
        # a patch that adds power to calculator/core.py and creates tests/test_power.py -> return == None
        # a patch of 4 files -> return == "patch touches 4 files, the limit is 3"
        # the rules after the one that refused are not called
        for rule in self.rules:
            reason = rule(patch, target_dir)
            if reason:
                return reason
        return None


sanity_service = SanityService(settings)
