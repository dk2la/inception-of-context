"""Live bonus events, kept in memory. The dashboard reads them over Server-Sent Events."""
import time


class BonusEventRepository:
    def __init__(self):
        # debug: self.events starts as []. The list lives in this process. A restart clears it.
        self.events = []

    def add(self, type, detail):
        """One thing the bonus Patch Loop or the Docker watcher did."""
        # debug: add("attempt", {"number": 1, "ok": True, "validation_ok": True, "error": None})
        # appends {"time": <unix seconds>, "type": "attempt", "detail": that dict}
        self.events.append({"time": time.time(), "type": type, "detail": detail})

    def since(self, count):
        """The events after the first count ones."""
        # debug: three events stored. since(0) returns all three. since(2) returns only the last one.
        # since(3) returns []. GET /bonus/events uses this so a sent event is not repeated.
        return self.events[count:]


bonus_event_repository = BonusEventRepository()
