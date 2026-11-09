import os

import pytest

# The real Target Project: the target/ folder, or TARGET_DIR (inside Docker it is /workspace).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_TARGET = os.environ.get("TARGET_DIR") or os.path.join(REPO_ROOT, "target")


@pytest.fixture
def real_target():
    return REAL_TARGET
