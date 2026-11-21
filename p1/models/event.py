"""An Event: one thing the Watcher did, shown live on the dashboard."""
from typing import TypedDict

EVENT_TYPES = ("indexed", "deleted")


class Event(TypedDict):
    time: float  # time.time() when it happened
    type: str  # one of EVENT_TYPES
    path: str  # the file, relative to the Target Project
    chunks: int  # how many Chunks the file has now
