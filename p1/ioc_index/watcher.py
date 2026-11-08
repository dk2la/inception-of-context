"""Filesystem watcher with debouncing and a polling safety net.

`native` uses inotify/FSEvents through watchdog. `polling` uses watchdog's
PollingObserver (needed on Docker bind mounts over btrfs/overlay where inotify
drops events). On top of either backend a periodic reconcile pass compares
(mtime, size) of every indexable file, so a missed event is caught within a
few seconds anyway.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from .indexer import Indexer

log = logging.getLogger("ioc.watcher")


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "Watcher") -> None:
        self.watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type in ("opened", "closed_no_write"):
            return
        paths = [event.src_path]
        if getattr(event, "dest_path", None):
            paths.append(event.dest_path)
        for p in paths:
            self.watcher.touch(p)


class Watcher:
    def __init__(self, indexer: Indexer, mode: str = "auto", poll_interval: float = 1.0,
                 debounce: float = 0.4, reconcile_interval: float = 5.0) -> None:
        self.indexer = indexer
        self.mode = mode
        self.poll_interval = poll_interval
        self.debounce = debounce
        self.reconcile_interval = reconcile_interval
        self.backend = "off"
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._observer = None
        self._threads: list[threading.Thread] = []
        self._fingerprint: dict[str, tuple[float, int]] = {}

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self.mode == "off":
            return
        target = str(self.indexer.settings.target)
        if self.mode in ("auto", "native"):
            try:
                obs = Observer()
                obs.schedule(_Handler(self), target, recursive=True)
                obs.start()
                self._observer, self.backend = obs, "native"
            except Exception as exc:                       # inotify limit, unsupported FS...
                log.warning("native watcher unavailable (%s), falling back to polling", exc)
        if self._observer is None:
            obs = PollingObserver(timeout=self.poll_interval)
            obs.schedule(_Handler(self), target, recursive=True)
            obs.start()
            self._observer, self.backend = obs, "polling"
        self._fingerprint = self._scan_fingerprint()
        for fn in (self._drain_loop, self._reconcile_loop):
            t = threading.Thread(target=fn, daemon=True, name=f"ioc-{fn.__name__}")
            t.start()
            self._threads.append(t)
        self.indexer.events.publish("watcher", backend=self.backend, target=target)

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)

    # ---------------------------------------------------------------- internals
    def touch(self, path: str) -> None:
        if self.indexer.filter.is_excluded_path(path):
            return
        with self._lock:
            self._pending[path] = time.monotonic()

    def _drain_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.1)
            now = time.monotonic()
            with self._lock:
                ready = [p for p, t in self._pending.items() if now - t >= self.debounce]
                for p in ready:
                    del self._pending[p]
            for p in sorted(ready):
                try:
                    self.indexer.handle_path(p)
                except Exception as exc:                   # never let the watcher die
                    log.exception("failed to handle %s", p)
                    self.indexer.events.publish("error", path=str(p), error=str(exc))

    def _scan_fingerprint(self) -> dict[str, tuple[float, int]]:
        fp = {}
        target = self.indexer.settings.target
        for rel in self.indexer.filter.walk():
            try:
                st = (target / rel).stat()
                fp[rel] = (st.st_mtime, st.st_size)
            except OSError:
                pass
        return fp

    def _reconcile_loop(self) -> None:
        if self.reconcile_interval <= 0:
            return
        while not self._stop.wait(self.reconcile_interval):
            try:
                current = self._scan_fingerprint()
                changed = [p for p, v in current.items() if self._fingerprint.get(p) != v]
                gone = [p for p in self._fingerprint if p not in current]
                self._fingerprint = current
                target = self.indexer.settings.target
                for rel in changed + gone:
                    self.touch(str(target / rel))
            except Exception:
                log.exception("reconcile pass failed")
