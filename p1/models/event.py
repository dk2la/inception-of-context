"""An Event: one thing the Watcher did, shown live on the dashboard."""
from typing import TypedDict

EVENT_TYPES = ("indexed", "deleted")


class Event(TypedDict):
    time: float
    type: str
    path: str
    chunks: int
