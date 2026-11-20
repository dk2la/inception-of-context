"""Sanity Checks: hard rules that refuse a Patch before anything touches the disk.

Each rule is a method (patch, target_dir) of SanityService that returns a reason string, or None if the Patch is fine.
A Patch looks like {"summary": ..., "files": [{"path": ..., "op": "create|modify|delete", "content": ...}]}.
"""
import ast
import os

from p1.config.settings import settings

MARKER = "=== FILE:"  # the line that starts each file in the Patch prompt; it must never reach a file


class SanityService:
    def __init__(self, settings):
        self.settings = settings
        # outside_target must stay first: the rules after it read files from disk and trust the paths are inside.
        # Then the cheap rules that only look at the Patch, then the ones that read files (empties_file before
        # shrinks_too_much, so "replaced by nothing" gets its more specific reason), then the one that parses code.
        self.rules = [self.outside_target, self.touches_config, self.targets_folder, self.too_many_files,
                      self.has_marker, self.creates_existing, self.weakens_tests, self.empties_file,
                      self.shrinks_too_much, self.stub_function]

    def outside_target(self, patch, target_dir):
        """Refuse absolute paths and paths with a '..' part (a backslash counts as a separator)."""
        for entry in patch["files"]:
            path = entry["path"].replace("\\", "/")
            if os.path.isabs(path) or ".." in path.split("/"):
                return f"path outside target project: {entry['path']}"
        return None

    def touches_config(self, patch, target_dir):
        """Refuse any change to ioc.config.yml, so the model cannot weaken the Validation Command."""
        for entry in patch["files"]:
            # lower(): on a case-insensitive disk (a macOS bind mount) IOC.config.yml is the same file
            if os.path.normpath(entry["path"].replace("\\", "/")).lower() == self.settings.VALIDATION_CONFIG.lower():
                return "the Patch may not change ioc.config.yml (it holds the Validation Command)"
        return None

    def targets_folder(self, patch, target_dir):
        """Refuse a path that is a folder: a Patch is made of files."""
        for entry in patch["files"]:
            if os.path.isdir(os.path.join(target_dir, entry["path"])):
                return f"{entry['path']} is a folder, not a file"
        return None

    def too_many_files(self, patch, target_dir):
        """Refuse a Patch that touches more than self.settings.MAX_FILES files (create, modify and delete all count)."""
        count = len(patch["files"])
        if count > self.settings.MAX_FILES:
            return f"patch touches {count} files, the limit is {self.settings.MAX_FILES}"
        return None

    def has_marker(self, patch, target_dir):
        """Refuse content with the prompt's file marker in it: the model copied its input."""
        for entry in patch["files"]:
            if MARKER in (entry.get("content") or ""):
                return f"retrieval marker '{MARKER}' found in {entry['path']}"
        return None

    def creates_existing(self, patch, target_dir):
        """Refuse a 'create' of a file that is already there: the model has a wrong picture of the project."""
        for entry in patch["files"]:
            if entry.get("op") == "create" and os.path.exists(os.path.join(target_dir, entry["path"])):
                return f"create on existing file: {entry['path']} (use modify)"
        return None

    def old_content(self, entry, target_dir):
        """The current text of the entry's file, or "" if there is no such file."""
        path = os.path.join(target_dir, entry["path"])
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def empties_file(self, patch, target_dir):
        """Refuse to modify a non-empty file into "", "None" or "null" (a JSON null counts as nothing too)."""
        for entry in patch["files"]:
            if entry.get("op") != "modify" or not self.old_content(entry, target_dir).strip():
                continue
            if (entry.get("content") or "").strip() in ("", "None", "null"):
                return f"patch would empty {entry['path']}"
        return None

    def shrinks_too_much(self, patch, target_dir):
        """Refuse a modify that cuts a file by more than self.settings.MAX_SHRINK percent: the model probably left out most of it."""
        for entry in patch["files"]:
            if entry.get("op") != "modify":
                continue
            old = self.old_content(entry, target_dir)
            new = entry.get("content") or ""
            if old.strip() and len(new) < len(old) * (100 - self.settings.MAX_SHRINK) / 100:
                shrink = round(100 - 100 * len(new) / len(old))
                return f"{entry['path']} would shrink by {shrink} % (limit {self.settings.MAX_SHRINK} %), send the whole file"
        return None

    def does_nothing(self, statement):
        """True for `pass`, `...` and `return None` (or a bare `return`)."""
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
        body = function.body
        if ast.get_docstring(function, clean=False) is not None:
            body = body[1:]
        return all(self.does_nothing(statement) for statement in body)

    def stub_function(self, patch, target_dir):
        """Refuse a Python function whose body does nothing: it can pass the tests while the feature is missing."""
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
        name = os.path.basename(path.replace("\\", "/"))
        return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))

    def tests_in(self, text):
        """{name: code} of every test function, also inside test classes. None if the text does not parse."""
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
        for entry in patch["files"]:
            if not self.is_test_file(entry["path"]) or not os.path.isfile(os.path.join(target_dir, entry["path"])):
                continue
            if entry.get("op") == "delete":
                return f"the Patch may not delete the test file {entry['path']}"
            old = self.tests_in(self.old_content(entry, target_dir))
            new = self.tests_in(entry.get("content") or "")
            if old is None or new is None:
                continue  # py_compile in the Validation Command reports broken code better
            for name in old:
                if name not in new:
                    return f"the Patch removes the test {name} from {entry['path']}"
                if new[name] != old[name]:
                    return f"the Patch changes the test {name} in {entry['path']} (add new tests instead)"
        return None

    def check_patch(self, patch, target_dir):
        """Return the reason of the first rule that refuses the Patch, or None if it is allowed."""
        for rule in self.rules:
            reason = rule(patch, target_dir)
            if reason:
                return reason
        return None


sanity_service = SanityService(settings)
