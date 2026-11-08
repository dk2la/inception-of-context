import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "p1"))

from ioc_index.app import build_context  # noqa: E402
from ioc_index.config import Settings   # noqa: E402


@pytest.fixture
def target(tmp_path) -> Path:
    dst = tmp_path / "target"
    shutil.copytree(ROOT / "demo", dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return dst


@pytest.fixture
def ctx(target, tmp_path):
    settings = Settings.from_env(target, chroma_path=tmp_path / "chroma", embedder=os.environ.get("IOC_TEST_EMBEDDER", "fake"),
                                 watch_mode="polling", poll_interval=0.2, debounce=0.1)
    c = build_context(settings)
    yield c
    c.stop()
