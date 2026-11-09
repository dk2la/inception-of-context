import time

import pytest

from p1 import index


# --- the event list ---


def test_add_event_appends_an_event_with_the_time_it_happened(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    before = time.time()
    index.add_event("indexed", "a.py", 3)
    assert len(index.EVENTS) == 1
    event = index.EVENTS[0]
    assert (event["type"], event["path"], event["chunks"]) == ("indexed", "a.py", 3)
    assert before <= event["time"] <= time.time()


def test_events_keep_the_order_they_were_added_in(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    index.add_event("indexed", "a.py", 1)
    index.add_event("deleted", "a.py", 0)
    assert [(e["type"], e["chunks"]) for e in index.EVENTS] == [("indexed", 1), ("deleted", 0)]


def test_add_event_refuses_an_unknown_type(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    with pytest.raises(ValueError):
        index.add_event("changed", "a.py", 1)
    assert index.EVENTS == []
