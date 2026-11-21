"""GET /events: the Watcher events as Server-Sent Events."""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from p1.services.overview import overview_service


class EventsView:
    def __init__(self, overview_service):
        self.overview_service = overview_service
        self.router = APIRouter()
        self.router.add_api_route("/events", self.events, methods=["GET"])

    def format_event(self, event):
        """One Server-Sent Events message: a "data:" line and an empty line."""
        return "data: " + json.dumps(event) + "\n\n"

    def event_stream(self):
        """Send the Watcher events: first those so far, then each new one, checking twice a second."""
        sent = 0
        while True:
            for event in self.overview_service.events_since(sent):
                yield self.format_event(event)
                sent += 1
            yield ": waiting\n\n"
            time.sleep(0.5)

    def events(self):
        return StreamingResponse(self.event_stream(), media_type="text/event-stream")


events_view = EventsView(overview_service)
