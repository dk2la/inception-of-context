"""GET /llm/live: what the model writes, sent to the browser while it writes it."""
import json

import p2.views.llm_live as llm_live_module
from p1.core.llm import llm_client
from p2.views.llm_live import llm_live_view


def state(model="coder", id=1, text="", done=False, error=None):
    return {"id": id, "model": model, "text": text, "done": done, "error": error, "started": 0.0}


def test_the_first_update_sends_the_text_so_far(monkeypatch):
    monkeypatch.setattr(llm_client, "live", {"coder": state(text='{"sum')})
    assert llm_live_view.updates({}) == [
        {"model": "coder", "id": 1, "reset": True, "delta": '{"sum', "done": False, "error": None}]


def test_later_updates_send_only_the_new_characters_then_done(monkeypatch):
    live = {"coder": state(text="ab")}
    monkeypatch.setattr(llm_client, "live", live)
    sent = {}
    llm_live_view.updates(sent)
    assert llm_live_view.updates(sent) == []
    live["coder"]["text"] = "abcd"
    assert [(m["reset"], m["delta"]) for m in llm_live_view.updates(sent)] == [(False, "cd")]
    live["coder"]["done"] = True
    assert llm_live_view.updates(sent) == [
        {"model": "coder", "id": 1, "reset": False, "delta": "", "done": True, "error": None}]
    assert llm_live_view.updates(sent) == []


def test_a_new_call_of_the_same_model_starts_over(monkeypatch):
    live = {"coder": state(text="old", done=True)}
    monkeypatch.setattr(llm_client, "live", live)
    sent = {}
    llm_live_view.updates(sent)
    live["coder"] = state(id=2, text="n")
    assert llm_live_view.updates(sent) == [
        {"model": "coder", "id": 2, "reset": True, "delta": "n", "done": False, "error": None}]


def test_the_stream_sends_updates_then_keeps_yielding(monkeypatch):
    monkeypatch.setattr(llm_client, "live", {"answer": state(model="answer", text="hi", done=True)})
    naps = []
    monkeypatch.setattr(llm_live_module.time, "sleep", naps.append)
    stream = llm_live_view.stream()
    message = next(stream)
    assert json.loads(message[len("data: "):])["delta"] == "hi"
    assert next(stream).startswith(":")
    assert next(stream).startswith(":")
    assert naps == [0.2]


def test_the_route_answers_as_an_event_stream(client, monkeypatch):
    monkeypatch.setattr(llm_live_view, "stream", lambda: iter(['data: {"delta": "x"}\n\n']))
    response = client.get("/llm/live")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == 'data: {"delta": "x"}\n\n'
