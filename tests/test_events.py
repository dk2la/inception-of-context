import json

from p1.repositories.event_repository import event_repository
import p1.views.events as events_view_module
from p1.views.events import events_view


def test_format_event_is_one_server_sent_message():
    event = {"time": 1731070995.12, "type": "indexed", "path": "calculator/core.py", "chunks": 6}
    message = events_view.format_event(event)
    assert message.startswith("data: ")
    assert message.endswith("\n\n")
    assert json.loads(message[len("data: "):]) == event


def test_event_stream_sends_the_events_so_far_in_order(monkeypatch):
    monkeypatch.setattr(event_repository, "events", [])
    event_repository.add_event("indexed", "a.py", 2)
    event_repository.add_event("deleted", "b.md", 0)
    stream = events_view.event_stream()
    first, second = json.loads(next(stream)[6:]), json.loads(next(stream)[6:])
    assert (first["type"], first["path"]) == ("indexed", "a.py")
    assert (second["type"], second["path"]) == ("deleted", "b.md")


def test_event_stream_sends_new_events_once_after_waiting_half_a_second(monkeypatch):
    monkeypatch.setattr(event_repository, "events", [])
    event_repository.add_event("indexed", "a.py", 2)
    naps = []
    monkeypatch.setattr(events_view_module.time, "sleep", naps.append)
    stream = events_view.event_stream()
    assert json.loads(next(stream)[6:])["path"] == "a.py"
    assert next(stream).startswith(":")
    event_repository.add_event("indexed", "later.py", 1)
    assert json.loads(next(stream)[6:])["path"] == "later.py"
    assert naps == [0.5]


def test_an_idle_event_stream_keeps_yielding_so_a_closed_connection_is_noticed(monkeypatch):
    """A stream that sleeps forever without yielding would block a server thread after the browser left."""
    monkeypatch.setattr(event_repository, "events", [])

    def blocked(seconds):
        raise AssertionError("the stream is sleeping instead of yielding")

    monkeypatch.setattr(events_view_module.time, "sleep", blocked)
    stream = events_view.event_stream()
    assert next(stream).startswith(":")


def test_two_streams_each_get_every_event(monkeypatch):
    monkeypatch.setattr(event_repository, "events", [])
    event_repository.add_event("indexed", "a.py", 2)
    one, other = events_view.event_stream(), events_view.event_stream()
    assert next(one) == next(other)


def test_events_route_answers_as_an_event_stream(client, monkeypatch):
    monkeypatch.setattr(events_view, "event_stream", lambda: iter([events_view.format_event({"type": "indexed"})]))
    response = client.get("/events")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == 'data: {"type": "indexed"}\n\n'
