import os

import pytest

# The real Target Project: the target/ folder, or TARGET_DIR (inside Docker it is /workspace).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_TARGET = os.environ.get("TARGET_DIR") or os.path.join(REPO_ROOT, "target")


@pytest.fixture
def real_target():
    return REAL_TARGET


@pytest.fixture
def temp_index(tmp_path, monkeypatch):
    """An empty temporary Target Project and Index, so tests never touch the real ones."""
    from p1 import index

    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(index, "TARGET_DIR", str(target))
    monkeypatch.setattr(index, "CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(index, "_collection", None)
    yield str(target)
