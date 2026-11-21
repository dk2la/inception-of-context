"""GET /bonus/events: live validation status as Server-Sent Events."""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from bonus.repositories.event_repository import bonus_event_repository


class BonusEventsView:
    def __init__(self, events):
        self.events = events
        self.router = APIRouter()
        self.router.add_api_route("/bonus/events", self.stream, methods=["GET"])

    def format_event(self, event):
        return "data: " + json.dumps(event) + "\n\n"

    def event_stream(self):
        sent = 0
        while True:
            for event in self.events.since(sent):
                yield self.format_event(event)
                sent += 1
            yield ": waiting\n\n"
            time.sleep(0.5)

    def stream(self):
        return StreamingResponse(self.event_stream(), media_type="text/event-stream")


bonus_events_view = BonusEventsView(bonus_event_repository)
