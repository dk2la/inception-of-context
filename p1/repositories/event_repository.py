"""What the Watcher did, kept in memory, oldest first. The dashboard reads it live."""
import time

from p1.models.event import EVENT_TYPES


class EventRepository:
    def __init__(self):
        # debug: self.events == []  # a plain list, not Chroma. Empty again after a restart.
        self.events = []

    def add_event(self, type, path, chunks):
        """Write down what the Watcher did: type is "indexed" or "deleted"."""
        # debug: called by the Watcher after reindex_file. The startup scan does not call this.
        # type == "indexed"   # or "deleted" when the file is gone. Anything else raises ValueError.
        # path == "calculator/core.py"
        # chunks == 5          # how many Chunks the file has now, an int. A deleted file has 0.
        # appended == {"time": 1740000000.0, "type": "indexed", "path": "calculator/core.py", "chunks": 5}
        # no return value. Oldest event stays at index 0.
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {type}")
        self.events.append({"time": time.time(), "type": type, "path": path, "chunks": chunks})

    def events_since(self, count):
        """The events after the first count ones."""
        # debug: count == 2  # how many events this reader has already seen
        # self.events == [event0, event1, event2]
        # return == [event2]  # self.events[count:]. count past the end returns [].
        # GET /events and "python -m p1.index --watch" both poll this every 0.5s.
        return self.events[count:]


event_repository = EventRepository()
