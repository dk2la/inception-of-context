"""What the Watcher did, kept in memory, oldest first. The dashboard reads it live."""
import time

from p1.models.event import EVENT_TYPES

EVENTS = []


def add_event(type, path, chunks):
    """Write down what the Watcher did: type is "indexed" or "deleted"."""
    if type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {type}")
    EVENTS.append({"time": time.time(), "type": type, "path": path, "chunks": chunks})


def events_since(count):
    """The events after the first count ones."""
    return EVENTS[count:]
