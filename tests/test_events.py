import json

from p1 import index
from p2 import app as app_module
from p2.app import event_stream, format_event


def test_format_event_is_one_server_sent_message():
    event = {"time": 1731070995.12, "type": "indexed", "path": "calculator/core.py", "chunks": 6}
    message = format_event(event)
    assert message.startswith("data: ")
    assert message.endswith("\n\n")
    assert json.loads(message[len("data: "):]) == event


def test_event_stream_sends_the_events_so_far_in_order(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    index.add_event("indexed", "a.py", 2)
    index.add_event("deleted", "b.md", 0)
    stream = event_stream()
    first, second = json.loads(next(stream)[6:]), json.loads(next(stream)[6:])
    assert (first["type"], first["path"]) == ("indexed", "a.py")
    assert (second["type"], second["path"]) == ("deleted", "b.md")


def test_event_stream_sends_new_events_once_after_waiting_half_a_second(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    index.add_event("indexed", "a.py", 2)
    naps = []
    monkeypatch.setattr(app_module.time, "sleep", naps.append)
    stream = event_stream()
    assert json.loads(next(stream)[6:])["path"] == "a.py"
    assert next(stream).startswith(":")  # nothing new: only a comment, a.py is not sent again
    index.add_event("indexed", "later.py", 1)  # the Watcher does something while the stream is waiting
    assert json.loads(next(stream)[6:])["path"] == "later.py"
    assert naps == [0.5]


def test_an_idle_event_stream_keeps_yielding_so_a_closed_connection_is_noticed(monkeypatch):
    """A stream that sleeps forever without yielding would block a server thread after the browser left."""
    monkeypatch.setattr(index, "EVENTS", [])

    def blocked(seconds):
        raise AssertionError("the stream is sleeping instead of yielding")

    monkeypatch.setattr(app_module.time, "sleep", blocked)
    stream = event_stream()
    assert next(stream).startswith(":")  # an SSE comment: the browser ignores it


def test_two_streams_each_get_every_event(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    index.add_event("indexed", "a.py", 2)
    one, other = event_stream(), event_stream()
    assert next(one) == next(other)


def test_events_route_answers_as_an_event_stream(client, monkeypatch):
    monkeypatch.setattr(app_module, "event_stream", lambda: iter([format_event({"type": "indexed"})]))
    response = client.get("/events")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == 'data: {"type": "indexed"}\n\n'
