"""Hard refusals checked before anything touches the disk."""
from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath

from ioc_index.walker import FileFilter

from .schema import Patch

MAX_FILES = 3
MAX_SHRINK = 0.60
RETRIEVAL_MARKERS = ("<<<IOC_", "IOC_END>>>", "### [", "\nFACTS:", "\nSNIPPETS:", "\nQUESTION:", "<|im_start|>", "<|endoftext|>")
EMPTY_VALUES = {"", "none", "null"}


def stub_functions(source: str) -> set[str] | None:
    """Qualified names of Python functions whose body is only pass / ... / return None. None if unparsable."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    stubs: set[str] = set()

    def is_stub_stmt(st: ast.stmt) -> bool:
        if isinstance(st, ast.Pass):
            return True
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and st.value.value is Ellipsis:
            return True
        if isinstance(st, ast.Return) and (st.value is None or (isinstance(st.value, ast.Constant) and st.value.value is None)):
            return True
        if isinstance(st, ast.Raise) and st.exc is not None:
            exc = st.exc.func if isinstance(st.exc, ast.Call) else st.exc
            return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"
        return False

    def visit(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stmts = list(node.body)
                if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) \
                        and isinstance(stmts[0].value.value, str):
                    stmts = stmts[1:]                      # a docstring alone is still a stub
                if not stmts or all(is_stub_stmt(s) for s in stmts):
                    stubs.add(prefix + node.name)
                visit(node.body, prefix + node.name + ".")
            elif isinstance(node, ast.ClassDef):
                visit(node.body, prefix + node.name + ".")
    visit(tree.body, "")
    return stubs


_JS_STUB = re.compile(r"(?:function\s+(\w+)\s*\([^)]*\)|(\w+)\s*\([^)]*\)\s*|(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)\s*\{\s*\}")


def _js_stubs(source: str) -> set[str]:
    return {next(g for g in m.groups() if g) for m in _JS_STUB.finditer(source)}


def check_patch(patch: Patch, target: Path, file_filter: FileFilter) -> list[str]:
    errors: list[str] = []
    if len(patch.files) > MAX_FILES:
        errors.append(f"patch touches {len(patch.files)} files; at most {MAX_FILES} are allowed at once")
    seen = set()
    for f in patch.files:
        if f.path in seen:
            errors.append(f"{f.path}: listed more than once")
        seen.add(f.path)
    target = target.resolve()
    for f in patch.files:
        pure = PurePosixPath(f.path)
        if pure.is_absolute() or ".." in pure.parts or not f.path:
            errors.append(f"{f.path}: path must be relative to the project root, without '..'")
            continue
        full = (target / f.path).resolve()
        try:
            full.relative_to(target)
        except ValueError:
            errors.append(f"{f.path}: path escapes the project root")
            continue
        if file_filter.is_excluded_path(full) or f.path.endswith(".ioc.tmp"):
            errors.append(f"{f.path}: refusing to write into an excluded/hidden/vendor location")
            continue
        exists = full.is_file()
        if full.exists() and not exists:
            errors.append(f"{f.path}: is a directory")
            continue
        if f.op == "create" and exists:
            errors.append(f"{f.path}: op 'create' but the file already exists (use 'modify' with the full new content)")
            continue
        if f.op in ("modify", "delete") and not exists:
            errors.append(f"{f.path}: op '{f.op}' but the file does not exist (use 'create' for new files)")
            continue
        if f.op == "delete":
            continue
        new = f.content or ""
        old = full.read_text(encoding="utf-8", errors="replace") if exists else ""
        for marker in RETRIEVAL_MARKERS:
            if marker in new:
                errors.append(f"{f.path}: content leaks a retrieval/prompt marker ({marker.strip()!r})")
                break
        if re.search(r"^```", new, re.M):
            errors.append(f"{f.path}: content contains a markdown code fence (```), not raw file content")
        if exists and old.strip() and new.strip().lower() in EMPTY_VALUES:
            errors.append(f"{f.path}: would replace a non-empty file with {new.strip()!r}")
            continue
        if exists and old.strip() and len(new.strip()) < (1 - MAX_SHRINK) * len(old.strip()):
            pct = round(100 * (1 - len(new.strip()) / len(old.strip())))
            errors.append(f"{f.path}: would shrink the file by {pct}% (more than {int(MAX_SHRINK * 100)}% is refused);"
                          " return the COMPLETE file, keeping the existing code")
        if exists and new == old:
            errors.append(f"{f.path}: 'modify' leaves the file unchanged")
        if f.path.endswith((".py", ".pyi")):
            new_stubs = stub_functions(new)
            if new_stubs:
                old_stubs = stub_functions(old) or set()
                fresh = sorted(new_stubs - old_stubs)
                if fresh:
                    errors.append(f"{f.path}: function body is only a stub (pass / ... / return None): {', '.join(fresh)}")
        elif f.path.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs")):
            fresh = sorted(_js_stubs(new) - _js_stubs(old))
            if fresh:
                errors.append(f"{f.path}: empty function body: {', '.join(fresh)}")
    return errors
