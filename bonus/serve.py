#!/usr/bin/env python3
"""Bonus entry point: the full system (parts 1-3) plus /reindex, dry-run diffs and auto git commit.

    IOC_AUTOCOMMIT=1 python bonus/serve.py [target] [--port 8000]
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "p3"), os.path.join(ROOT, "p2"), os.path.join(ROOT, "p1")]

from ioc_index.app import build_context      # noqa: E402
from ioc_index.config import Settings        # noqa: E402
from ioc_bonus.server import create_app      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Inception-of-Context with bonus features")
    ap.add_argument("target", nargs="?", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    settings = Settings.from_env(args.target, port=args.port)
    import uvicorn
    uvicorn.run(create_app(build_context(settings)), host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
