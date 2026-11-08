"""Unified diffs of a patch against the files on disk (or a captured baseline)."""
from __future__ import annotations

import difflib
from pathlib import Path

from ioc_patch.schema import Patch


def file_diff(path: str, old: str | None, new: str | None) -> str:
    a = (old or "").splitlines(keepends=True)
    b = (new or "").splitlines(keepends=True)
    if new and not new.endswith("\n"):
        b = (new + "\n").splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile="/dev/null" if old is None else f"a/{path}",
                                        tofile="/dev/null" if new is None else f"b/{path}"))


def patch_diff(patch: Patch, target: Path, baseline: dict[str, str | None] | None = None) -> list[dict]:
    out = []
    for f in patch.files:
        if baseline is not None and f.path in baseline:
            old = baseline[f.path]
        else:
            p = target / f.path
            old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        new = None if f.op == "delete" else (f.content or "")
        d = file_diff(f.path, old, new)
        out.append({"path": f.path, "op": f.op, "diff": d,
                    "added": sum(1 for l in d.splitlines() if l.startswith("+") and not l.startswith("+++")),
                    "removed": sum(1 for l in d.splitlines() if l.startswith("-") and not l.startswith("---"))})
    return out
