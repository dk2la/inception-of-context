import pytest

from p1.config import settings
from p1.core import llm


def test_replies_come_back_in_order_and_prompts_are_recorded(fake_llm):
    fake_llm.replies = ["a", "b"]
    assert llm.call_llm("m", "p1") == "a"
    assert llm.call_llm("m", "p2", json_mode=True) == "b"
    assert fake_llm.prompts == [("m", "p1", False), ("m", "p2", True)]


def test_calling_without_a_reply_fails_loudly(fake_llm):
    with pytest.raises(AssertionError, match="no reply left"):
        llm.call_llm("m", "p")


def test_the_fake_can_raise_an_error(fake_llm):
    fake_llm.error = llm.LLMError("down")
    with pytest.raises(llm.LLMError, match="down"):
        llm.call_llm("m", "p")


def test_the_real_function_is_back_without_the_fixture(monkeypatch):
    assert llm.call_llm.__module__ == "p1.core.llm"
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(llm.LLMError):
        llm.call_llm("m", "p")
