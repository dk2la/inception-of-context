"""GET /events: the Watcher events as Server-Sent Events."""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from p1.services.overview import overview_service


class EventsView:
    def __init__(self, overview_service):
        # debug: registers GET /events. The dashboard opens it with new EventSource("/events").
        self.overview_service = overview_service
        self.router = APIRouter()
        self.router.add_api_route("/events", self.events, methods=["GET"])

    def format_event(self, event):
        """One Server-Sent Events message: a "data:" line and an empty line."""
        # debug: event == {"time": 1740000000.0, "type": "indexed", "path": "calculator/core.py", "chunks": 5}
        # return == 'data: {"time": 1740000000.0, "type": "indexed", "path": "calculator/core.py", "chunks": 5}\n\n'
        return "data: " + json.dumps(event) + "\n\n"

    def event_stream(self):
        """Send the Watcher events: first those so far, then each new one, checking twice a second."""
        # debug: one generator per open browser tab. sent starts at 0, so the first loop sends the whole journal.
        # events_since(0) == [event0, event1]. Each is yielded, then sent == 2.
        # next loop: events_since(2) == []. Nothing new, so only ": waiting\n\n" is yielded.
        # half a second later a save happens: events_since(2) == [the new indexed event], sent becomes 3.
        # The ": waiting" line is an SSE comment. The browser ignores it. Yielding it is what lets the
        # server notice the tab was closed. Without a yield here the loop would never return.
        sent = 0  # how many events this connection has received
        while True:
            for event in self.overview_service.events_since(sent):
                yield self.format_event(event)
                sent += 1
            # A comment line: the browser ignores it, but yielding lets the server notice a closed connection.
            # Without it this loop would never return and would keep a server thread busy after the browser left.
            yield ": waiting\n\n"
            time.sleep(0.5)

    def events(self):
        # debug: return is a StreamingResponse, media_type == "text/event-stream".
        # The body is event_stream(), which stays open. This is not one JSON response.
        return StreamingResponse(self.event_stream(), media_type="text/event-stream")


events_view = EventsView(overview_service)
