#!/usr/bin/env python3
"""Part 3 entry point: everything from parts 1-2 plus the generate/apply/validate loop.

    python p3/serve.py [target] [--port 8000]
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "p2"), os.path.join(ROOT, "p1")]

from ioc_index.app import build_context      # noqa: E402
from ioc_index.config import Settings        # noqa: E402
from ioc_patch.server import create_app      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Inception-of-Context: full system (part 3)")
    ap.add_argument("target", nargs="?", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    settings = Settings.from_env(args.target, port=args.port)
    import uvicorn
    uvicorn.run(create_app(build_context(settings)), host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
