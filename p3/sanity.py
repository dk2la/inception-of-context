"""Sanity Checks: hard rules that refuse a Patch before anything touches the disk.

Each rule is a function (patch, target_dir) that returns a reason string, or None if the Patch is fine.
A Patch looks like {"summary": ..., "files": [{"path": ..., "op": "create|modify|delete", "content": ...}]}.
"""
import ast
import os

MAX_FILES = 3
MAX_SHRINK = 60  # percent


def outside_target(patch, target_dir):
    """Refuse absolute paths and paths with a '..' part (a backslash counts as a separator)."""
    for entry in patch["files"]:
        path = entry["path"].replace("\\", "/")
        if os.path.isabs(path) or ".." in path.split("/"):
            return f"path outside target project: {entry['path']}"
    return None


def touches_config(patch, target_dir):
    """Refuse any change to ioc.config.yml, so the model cannot weaken the Validation Command."""
    for entry in patch["files"]:
        if os.path.normpath(entry["path"].replace("\\", "/")) == "ioc.config.yml":
            return "the Patch may not change ioc.config.yml (it holds the Validation Command)"
    return None


def too_many_files(patch, target_dir):
    """Refuse a Patch that touches more than MAX_FILES files (create, modify and delete all count)."""
    count = len(patch["files"])
    if count > MAX_FILES:
        return f"patch touches {count} files, the limit is {MAX_FILES}"
    return None


def creates_existing(patch, target_dir):
    """Refuse a 'create' of a file that is already there: the model has a wrong picture of the project."""
    for entry in patch["files"]:
        if entry.get("op") == "create" and os.path.exists(os.path.join(target_dir, entry["path"])):
            return f"create on existing file: {entry['path']} (use modify)"
    return None


def old_content(entry, target_dir):
    """The current text of the entry's file, or "" if there is no such file."""
    path = os.path.join(target_dir, entry["path"])
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def empties_file(patch, target_dir):
    """Refuse to modify a non-empty file into "", "None" or "null" (a JSON null counts as nothing too)."""
    for entry in patch["files"]:
        if entry.get("op") != "modify" or not old_content(entry, target_dir).strip():
            continue
        if (entry.get("content") or "").strip() in ("", "None", "null"):
            return f"patch would empty {entry['path']}"
    return None


def shrinks_too_much(patch, target_dir):
    """Refuse to modify a file into less than 40 % of its length: the model probably left out most of it."""
    for entry in patch["files"]:
        if entry.get("op") != "modify":
            continue
        old = old_content(entry, target_dir)
        new = entry.get("content") or ""
        if old.strip() and len(new) < len(old) * (100 - MAX_SHRINK) / 100:
            shrink = round(100 - 100 * len(new) / len(old))
            return f"{entry['path']} would shrink by {shrink} % (limit {MAX_SHRINK} %), send the whole file"
    return None


def does_nothing(statement):
    """True for `pass`, `...` and `return None` (or a bare `return`)."""
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr):  # `...` is an expression statement holding the constant Ellipsis
        return isinstance(statement.value, ast.Constant) and statement.value.value is Ellipsis
    if isinstance(statement, ast.Return):
        value = statement.value
        return value is None or (isinstance(value, ast.Constant) and value.value is None)
    return False


def is_stub(function):
    """True if the body of a function, its docstring aside, does nothing."""
    body = function.body
    if ast.get_docstring(function, clean=False) is not None:
        body = body[1:]
    return all(does_nothing(statement) for statement in body)


def stub_function(patch, target_dir):
    """Refuse a Python function whose body does nothing: it can pass the tests while the feature is missing."""
    for entry in patch["files"]:
        if entry.get("op") not in ("create", "modify") or not entry["path"].endswith(".py"):
            continue
        try:
            tree = ast.parse(entry.get("content") or "")
        except (SyntaxError, ValueError):
            continue  # py_compile in the Validation Command reports broken code better
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_stub(node):
                return f"stub function {node.name} in {entry['path']}"
    return None


# outside_target must stay first: the rules after it read files from disk and trust the paths are inside.
RULES = [outside_target, touches_config, too_many_files, creates_existing, empties_file, shrinks_too_much,
         stub_function]


def check_patch(patch, target_dir):
    """Return the reason of the first rule that refuses the Patch, or None if it is allowed."""
    for rule in RULES:
        reason = rule(patch, target_dir)
        if reason:
            return reason
    return None
