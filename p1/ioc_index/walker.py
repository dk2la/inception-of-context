"""Decides which files of the target are indexable and walks the tree."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
}
SKIP_SUFFIXES = {
    ".ioc.tmp", ".pyc", ".pyo", ".so", ".o", ".a", ".dll", ".dylib", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tar",
    ".whl", ".onnx", ".gguf", ".sqlite3", ".db", ".lock",
}


class FileFilter:
    """Path rules shared by the full scan and the watcher."""

    def __init__(self, target: Path, excluded: list[Path] | None = None, max_bytes: int = 512 * 1024):
        self.target = target.resolve()
        self.excluded = [p.resolve() for p in (excluded or [])]
        self.max_bytes = max_bytes

    def rel(self, path: str | os.PathLike) -> str | None:
        """Target-relative POSIX path, or None when the path is outside the target."""
        p = Path(os.path.abspath(path if Path(path).is_absolute() else self.target / path))
        for candidate in (p, p.resolve() if p.exists() else p):
            try:
                rel = candidate.relative_to(self.target).as_posix()
                return rel if rel != "." else ""
            except ValueError:
                continue
        return None

    def is_excluded_path(self, path: str | os.PathLike) -> bool:
        """True for anything we must never index or react to (dir rules, store folder, temp files)."""
        p = Path(os.path.abspath(path if Path(path).is_absolute() else self.target / path))
        for ex in self.excluded:
            if p == ex or ex in p.parents:
                return True
        rel = self.rel(p)
        if not rel:
            return True
        parts = rel.split("/")
        for part in parts[:-1]:
            if part in SKIP_DIRS or part.startswith("."):
                return True
        name = parts[-1]
        if name in SKIP_DIRS or name.startswith("."):
            return True
        return any(name.endswith(sfx) for sfx in SKIP_SUFFIXES)

    def is_indexable_file(self, path: str | os.PathLike) -> bool:
        p = Path(path)
        if not p.is_absolute():
            p = self.target / p
        if self.is_excluded_path(p) or not p.is_file():
            return False
        try:
            if p.stat().st_size > self.max_bytes:
                return False
            return not is_binary(p)
        except OSError:
            return False

    def walk(self) -> Iterator[str]:
        """Yield target-relative paths of every indexable file, sorted for stable output."""
        out: list[str] = []
        for root, dirs, files in os.walk(self.target):
            root_p = Path(root)
            dirs[:] = sorted(d for d in dirs if not self.is_excluded_path(root_p / d))
            for f in files:
                full = root_p / f
                if self.is_indexable_file(full):
                    out.append(full.relative_to(self.target).as_posix())
        yield from sorted(out)


def is_binary(path: Path, probe: int = 8192) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(probe)
    if b"\0" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # a multi-byte character cut at the probe boundary is still text
        return exc.start < len(head) - 4
    return False


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
