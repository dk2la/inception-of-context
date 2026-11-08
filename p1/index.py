#!/usr/bin/env python3
"""Part 1 entry point.

    python p1/index.py <target>             # index once and exit
    python p1/index.py <target> --watch     # index, then keep the collection in sync
    python p1/index.py <target> --serve     # index + watch + dashboard (Overview, Files)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ioc_index.app import build_context          # noqa: E402
from ioc_index.config import Settings            # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inception-of-Context indexer (part 1)")
    ap.add_argument("target", nargs="?", default=None, help="target project directory (default $IOC_TARGET or ./demo)")
    ap.add_argument("--chroma", default=None, help="ChromaDB persist directory (default $IOC_CHROMA_PATH)")
    ap.add_argument("--watch", action="store_true", help="keep watching the target after indexing")
    ap.add_argument("--serve", action="store_true", help="also serve the dashboard + API")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--reset", action="store_true", help="drop the collection before indexing")
    args = ap.parse_args(argv)

    from pathlib import Path
    settings = Settings.from_env(args.target, chroma_path=Path(args.chroma).resolve() if args.chroma else None,
                                 port=args.port)
    ctx = build_context(settings)
    if args.reset:
        ctx.store.reset()

    if args.serve:
        import uvicorn
        from ioc_index.server import create_app
        uvicorn.run(create_app(ctx), host=settings.host, port=settings.port, log_level="info")
        return 0

    stats = ctx.indexer.full_sync()
    print(f"indexed {stats['files']} files -> {stats['chunks']} chunks "
          f"(+{stats['added']} new, ~{stats['updated']} changed, -{stats['removed']} removed, "
          f"{stats['unchanged']} unchanged) in {stats['seconds']}s")
    print(f"collection '{settings.collection}' persisted at {settings.chroma_path}")
    if args.watch:
        ctx.watcher.start()
        print(f"watching {settings.target} ({ctx.watcher.backend}); Ctrl-C to stop")
        seen = ctx.events.last_seq
        try:
            while True:
                for ev in ctx.events.wait(seen, 1.0):
                    seen = ev["seq"]
                    print(f"[{ev['type']}] " + " ".join(f"{k}={v}" for k, v in ev.items()
                                                        if k not in ("seq", "ts", "type")))
        except KeyboardInterrupt:
            ctx.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
