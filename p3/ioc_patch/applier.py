"""Snapshot, atomic apply, byte-for-byte rollback."""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .schema import Patch

TMP_SUFFIX = ".ioc.tmp"


class Snapshot:
    """Remembers the exact bytes (or absence) of every file a loop touches, before the first write."""

    def __init__(self, target: Path) -> None:
        self.target = target
        self.files: dict[str, bytes | None] = {}
        self.modes: dict[str, int] = {}
        self.created_dirs: list[Path] = []

    def capture(self, rel: str) -> None:
        if rel in self.files:
            return                                    # keep the state from *before the loop*
        p = self.target / rel
        if p.is_file():
            self.files[rel] = p.read_bytes()
            self.modes[rel] = stat.S_IMODE(p.stat().st_mode)
        else:
            self.files[rel] = None

    def restore(self) -> list[str]:
        restored = []
        for rel, data in self.files.items():
            p = self.target / rel
            tmp = p.with_name(p.name + TMP_SUFFIX)
            if tmp.exists():
                tmp.unlink()
            if data is None:
                if p.exists():
                    p.unlink()
                    restored.append(rel)
                continue
            if p.is_file() and p.read_bytes() == data:
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, self.modes.get(rel, 0o644))
            os.replace(tmp, p)
            restored.append(rel)
        for d in sorted(self.created_dirs, key=lambda x: len(x.parts), reverse=True):
            try:
                d.rmdir()                                  # only if empty
            except OSError:
                pass
        return restored

    def verify(self) -> bool:
        for rel, data in self.files.items():
            p = self.target / rel
            if data is None:
                if p.exists():
                    return False
            elif not p.is_file() or hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256(data).digest():
                return False
        return True


def apply_patch(patch: Patch, target: Path, snapshot: Snapshot) -> list[str]:
    """Write every change to *.ioc.tmp first; only when all are staged, os.replace them into place."""
    for f in patch.files:
        snapshot.capture(f.path)
    staged: list[tuple[Path, Path]] = []
    try:
        for f in patch.files:
            if f.op == "delete":
                continue
            final = target / f.path
            missing = []
            parent = final.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            final.parent.mkdir(parents=True, exist_ok=True)
            snapshot.created_dirs.extend(missing)
            content = f.content or ""
            if content and not content.endswith("\n"):
                content += "\n"
            tmp = final.with_name(final.name + TMP_SUFFIX)
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            if final.is_file():
                os.chmod(tmp, stat.S_IMODE(final.stat().st_mode))
            staged.append((tmp, final))
    except Exception:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        for f in patch.files:
            (target / (f.path + TMP_SUFFIX)).unlink(missing_ok=True)
        raise
    for tmp, final in staged:                          # every temporary is ready: commit
        os.replace(tmp, final)
    for f in patch.files:
        if f.op == "delete":
            (target / f.path).unlink()
    return patch.paths
