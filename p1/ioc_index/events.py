"""In-memory activity feed shared by the watcher, the indexer and the API (SSE)."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

log = logging.getLogger("ioc")


class EventBus:
    def __init__(self, maxlen: int = 500) -> None:
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._seq = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    def publish(self, type_: str, **data) -> dict:
        with self._cond:
            self._seq += 1
            event = {"seq": self._seq, "ts": time.time(), "type": type_, **data}
            self._events.append(event)
            self._cond.notify_all()
        log.info("%s %s", type_, {k: v for k, v in data.items() if k != "detail"})
        return event

    @property
    def last_seq(self) -> int:
        return self._seq

    def since(self, seq: int, limit: int = 200) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e["seq"] > seq][-limit:]

    def recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._events)[-n:]

    def wait(self, seq: int, timeout: float) -> list[dict]:
        """Block until something newer than `seq` exists (or timeout)."""
        with self._cond:
            if self._seq <= seq:
                self._cond.wait(timeout)
        return self.since(seq)
