import os
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_TARGET = os.environ.get("TARGET_DIR") or os.path.join(REPO_ROOT, "target")


@pytest.fixture
def real_target():
    return REAL_TARGET


@pytest.fixture
def temp_index(tmp_path, monkeypatch):
    """An empty temporary Target Project and Index, so tests never touch the real ones."""
    from p1.config.settings import settings
    from p1.core.chroma_db import chroma_db

    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(settings, "TARGET_DIR", str(target))
    monkeypatch.setattr(settings, "CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(chroma_db, "_collection", None)
    yield str(target)


@pytest.fixture
def client(temp_index):
    """An HTTP client for the app, over an indexed temporary copy of the Target Project.

    The client is not used as a context manager, so the app's startup (and the Watcher) does not run.
    """
    from fastapi.testclient import TestClient

    from p1.services.indexer import indexer_service
    from p3.app import app

    shutil.copytree(REAL_TARGET, temp_index, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    indexer_service.index_all()
    return TestClient(app)


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model with scripted replies: set fake_llm.replies; read fake_llm.prompts afterwards."""
    from types import SimpleNamespace

    from p1.core.llm import llm_client

    fake = SimpleNamespace(replies=[], prompts=[], error=None)

    def call_llm(model, prompt, json_mode=False):
        fake.prompts.append((model, prompt, json_mode))
        if fake.error:
            raise fake.error
        assert fake.replies, f"fake_llm: no reply left for prompt: {prompt[:200]}"
        return fake.replies.pop(0)

    monkeypatch.setattr(llm_client, "call_llm", call_llm)
    return fake
