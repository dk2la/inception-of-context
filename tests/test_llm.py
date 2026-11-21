import io
import json

import pytest

from p1.config.settings import settings
import p1.core.llm as llm_module
from p1.core.llm import llm_client


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def fake_urlopen(sent, reply=b'{"response": "hello"}'):
    def urlopen(request, timeout=None):
        sent.append(request)
        return FakeResponse(reply)

    return urlopen


def test_call_llm_returns_the_text_of_the_reply(monkeypatch):
    sent = []
    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen(sent))
    assert llm_client.call_llm(settings.ANSWER_MODEL, "Say hi") == "hello"
    body = json.loads(sent[0].data)
    assert sent[0].full_url == settings.OLLAMA_HOST + "/api/generate"
    assert body == {"model": "qwen2.5:3b", "prompt": "Say hi", "stream": True}


def test_json_mode_asks_for_json_output(monkeypatch):
    sent = []
    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen(sent))
    llm_client.call_llm(settings.PATCH_MODEL, "p", json_mode=True)
    assert json.loads(sent[0].data)["format"] == "json"


def test_unreachable_ollama_raises_llm_error_naming_the_host(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(llm_module.LLMError, match="127.0.0.1:9"):
        llm_client.call_llm(settings.ANSWER_MODEL, "hi")


def test_http_error_raises_llm_error_with_a_hint(monkeypatch):
    def urlopen(request, timeout=None):
        raise llm_module.urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm_module.LLMError, match="make models"):
        llm_client.call_llm(settings.ANSWER_MODEL, "hi")


def test_timeout_raises_llm_error(monkeypatch):
    def urlopen(request, timeout=None):
        raise TimeoutError("too slow")

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm_module.LLMError):
        llm_client.call_llm(settings.ANSWER_MODEL, "hi")


# --- streaming: the reply arrives in pieces, and GET /llm/live can read it while it is written ---


def test_a_streamed_reply_is_joined_and_kept_as_the_live_output(monkeypatch):
    lines = b'{"response": "Hel", "done": false}\n\n{"response": "lo", "done": true}\n{"response": "ignored"}\n'
    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen([], lines))
    assert llm_client.call_llm(settings.ANSWER_MODEL, "hi") == "Hello"
    live = {state["model"]: state for state in llm_client.live_snapshot()}[settings.ANSWER_MODEL]
    assert live["text"] == "Hello"
    assert live["done"] is True
    assert live["error"] is None


def test_each_call_gets_a_new_live_id(monkeypatch):
    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen([]))
    llm_client.call_llm(settings.PATCH_MODEL, "a")
    first = {s["model"]: s for s in llm_client.live_snapshot()}[settings.PATCH_MODEL]["id"]
    llm_client.call_llm(settings.PATCH_MODEL, "b")
    assert {s["model"]: s for s in llm_client.live_snapshot()}[settings.PATCH_MODEL]["id"] == first + 1


def test_an_error_line_in_the_stream_raises_llm_error(monkeypatch):
    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen([], b'{"error": "model not found"}\n'))
    with pytest.raises(llm_module.LLMError, match="model not found"):
        llm_client.call_llm(settings.ANSWER_MODEL, "hi")
    live = {s["model"]: s for s in llm_client.live_snapshot()}[settings.ANSWER_MODEL]
    assert live["done"] is True
    assert "model not found" in live["error"]


def test_an_http_error_is_kept_in_the_live_output(monkeypatch):
    def urlopen(request, timeout=None):
        raise llm_module.urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm_module.LLMError):
        llm_client.call_llm(settings.PATCH_MODEL, "hi")
    live = {s["model"]: s for s in llm_client.live_snapshot()}[settings.PATCH_MODEL]
    assert "500" in live["error"] and live["done"] is True
