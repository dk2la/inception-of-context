"""GET /bonus/events: live validation status as Server-Sent Events."""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from bonus.repositories.event_repository import bonus_event_repository


class BonusEventsView:
    def __init__(self, events):
        # debug: one route, GET /bonus/events. events is the in-memory bonus_event_repository.
        self.events = events
        self.router = APIRouter()
        self.router.add_api_route("/bonus/events", self.stream, methods=["GET"])

    def format_event(self, event):
        # debug: event == {"time": 1.0, "type": "attempt", "detail": {"number": 1, "ok": False}}
        # return == 'data: {"time": 1.0, "type": "attempt", "detail": {"number": 1, "ok": false}}\n\n'
        return "data: " + json.dumps(event) + "\n\n"

    def event_stream(self):
        # debug: each new event is yielded as "data: ...\n\n". Then ": waiting\n\n" every 0.5s.
        # sent grows, so the same attempt event is not sent twice.
        sent = 0
        while True:
            for event in self.events.since(sent):
                yield self.format_event(event)
                sent += 1
            yield ": waiting\n\n"
            time.sleep(0.5)

    def stream(self):
        # debug: GET /bonus/events. media_type == "text/event-stream". The body is event_stream().
        return StreamingResponse(self.event_stream(), media_type="text/event-stream")


bonus_events_view = BonusEventsView(bonus_event_repository)
