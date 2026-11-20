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
    assert body == {"model": "qwen2.5:3b", "prompt": "Say hi", "stream": False}


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
