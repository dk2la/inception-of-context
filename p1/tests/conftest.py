import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent)]

from ioc_fixtures import ctx, target  # noqa: E402,F401
