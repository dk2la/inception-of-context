"""Live bonus events, kept in memory. The dashboard reads them over Server-Sent Events."""
import time


class BonusEventRepository:
    def __init__(self):
        self.events = []

    def add(self, type, detail):
        """One thing the bonus Patch Loop or the Docker watcher did."""
        self.events.append({"time": time.time(), "type": type, "detail": detail})

    def since(self, count):
        """The events after the first count ones."""
        return self.events[count:]


bonus_event_repository = BonusEventRepository()
