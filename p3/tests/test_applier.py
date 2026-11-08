import os

import pytest

from ioc_patch.applier import Snapshot, apply_patch
from ioc_patch.schema import parse_patch


def tree(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root)] = open(p, "rb").read()
    return out


def test_apply_then_restore_is_byte_for_byte(target):
    before = tree(target)
    p = parse_patch({"summary": "s", "files": [
        {"path": "main.py", "op": "modify", "content": "print('changed')"},
        {"path": "pkg/sub/new.py", "op": "create", "content": "X = 1\n"},
        {"path": "notes/cli.py", "op": "delete"}]})
    snap = Snapshot(target)
    apply_patch(p, target, snap)
    assert (target / "main.py").read_text() == "print('changed')\n"
    assert (target / "pkg/sub/new.py").exists() and not (target / "notes/cli.py").exists()
    assert not list(target.rglob("*.ioc.tmp"))
    snap.restore()
    assert snap.verify() and tree(target) == before
    assert not (target / "pkg").exists()


def test_snapshot_keeps_the_original_across_attempts(target):
    orig = (target / "main.py").read_bytes()
    snap = Snapshot(target)
    apply_patch(parse_patch({"files": [{"path": "main.py", "op": "modify", "content": "a = 1"}]}), target, snap)
    apply_patch(parse_patch({"files": [{"path": "main.py", "op": "modify", "content": "a = 2"}]}), target, snap)
    snap.restore()
    assert (target / "main.py").read_bytes() == orig


def test_failure_while_staging_writes_nothing(target, monkeypatch):
    before = tree(target)
    p = parse_patch({"files": [{"path": "main.py", "op": "modify", "content": "a = 1"},
                               {"path": "notes/service.py", "op": "modify", "content": "b = 2"}]})
    real_open = open
    calls = {"n": 0}

    def flaky_open(path, *a, **kw):
        if str(path).endswith(".ioc.tmp"):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk full")
        return real_open(path, *a, **kw)
    monkeypatch.setattr("builtins.open", flaky_open)
    with pytest.raises(OSError):
        apply_patch(p, target, Snapshot(target))
    monkeypatch.undo()
    assert tree(target) == before            # first file was only staged, never replaced
