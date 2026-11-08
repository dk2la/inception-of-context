import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "p1"), str(ROOT / "p2"), str(ROOT / "p3"), str(ROOT / "p1" / "tests")]

from ioc_fixtures import ctx, target  # noqa: E402,F401
