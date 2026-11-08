"""Wiring: builds the shared context (one Chroma client per process) used by every part."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from .config import Settings
from .embedder import Embedder, make_embedder
from .events import EventBus
from .indexer import Indexer
from .store import Store
from .watcher import Watcher


@dataclass
class Context:
    settings: Settings
    embedder: Embedder
    store: Store
    events: EventBus
    indexer: Indexer
    watcher: Watcher
    extras: dict = field(default_factory=dict)      # later parts hang their services here

    def start(self, background: bool = True) -> None:
        """Initial sync, then start watching. Background so the HTTP server comes up immediately."""
        def run() -> None:
            try:
                self.indexer.full_sync()
            except Exception as exc:
                logging.getLogger("ioc").exception("initial sync failed")
                self.events.publish("error", error=f"initial sync failed: {exc}")
                self.indexer.state = "error"
            self.watcher.start()
        if background:
            threading.Thread(target=run, daemon=True, name="ioc-initial-sync").start()
        else:
            run()

    def stop(self) -> None:
        self.watcher.stop()


def build_context(settings: Settings) -> Context:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.target.is_dir():
        raise SystemExit(f"target directory not found: {settings.target}")
    embedder = make_embedder(settings.embedder, settings.embed_cache)
    store = Store(settings.chroma_path, settings.collection, embed_model=embedder.name)
    events = EventBus()
    indexer = Indexer(settings, store, embedder, events)
    watcher = Watcher(indexer, mode=settings.watch_mode, poll_interval=settings.poll_interval,
                      debounce=settings.debounce)
    return Context(settings, embedder, store, events, indexer, watcher)
