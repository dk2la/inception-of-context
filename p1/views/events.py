"""GET /events: the Watcher events as Server-Sent Events."""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from p1.services import overview

router = APIRouter()


def format_event(event):
    """One Server-Sent Events message: a "data:" line and an empty line."""
    return "data: " + json.dumps(event) + "\n\n"


def event_stream():
    """Send the Watcher events: first those so far, then each new one, checking twice a second."""
    sent = 0  # how many events this connection has received
    while True:
        for event in overview.events_since(sent):
            yield format_event(event)
            sent += 1
        # A comment line: the browser ignores it, but yielding lets the server notice a closed connection.
        # Without it this loop would never return and would keep a server thread busy after the browser left.
        yield ": waiting\n\n"
        time.sleep(0.5)


@router.get("/events")
def events():
    return StreamingResponse(event_stream(), media_type="text/event-stream")
