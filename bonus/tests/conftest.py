import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ("p1", "p2", "p3", "bonus", "p1/tests")]

from ioc_fixtures import ctx, target  # noqa: E402,F401
