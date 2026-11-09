import os
import shutil

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


@pytest.fixture
def client(temp_index):
    """An HTTP client for the app, over an indexed temporary copy of the Target Project.

    The client is not used as a context manager, so the app's startup (and the Watcher) does not run.
    """
    from fastapi.testclient import TestClient

    from p1 import index
    from p2.app import app

    shutil.copytree(REAL_TARGET, temp_index, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    index.index_all()
    return TestClient(app)
