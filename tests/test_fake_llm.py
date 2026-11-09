import pytest

from p2 import ask


def test_replies_come_back_in_order_and_prompts_are_recorded(fake_llm):
    fake_llm.replies = ["a", "b"]
    assert ask.call_llm("m", "p1") == "a"
    assert ask.call_llm("m", "p2", json_mode=True) == "b"
    assert fake_llm.prompts == [("m", "p1", False), ("m", "p2", True)]


def test_calling_without_a_reply_fails_loudly(fake_llm):
    with pytest.raises(AssertionError, match="no reply left"):
        ask.call_llm("m", "p")


def test_the_fake_can_raise_an_error(fake_llm):
    fake_llm.error = ask.LLMError("down")
    with pytest.raises(ask.LLMError, match="down"):
        ask.call_llm("m", "p")


def test_the_real_function_is_back_without_the_fixture(monkeypatch):
    assert ask.call_llm.__module__ == "p2.ask"
    monkeypatch.setattr(ask, "OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(ask.LLMError):
        ask.call_llm("m", "p")
