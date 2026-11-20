import pytest

from p1.config.settings import settings
import p1.core.llm as llm_module
from p1.core.llm import llm_client


def test_replies_come_back_in_order_and_prompts_are_recorded(fake_llm):
    fake_llm.replies = ["a", "b"]
    assert llm_client.call_llm("m", "p1") == "a"
    assert llm_client.call_llm("m", "p2", json_mode=True) == "b"
    assert fake_llm.prompts == [("m", "p1", False), ("m", "p2", True)]


def test_calling_without_a_reply_fails_loudly(fake_llm):
    with pytest.raises(AssertionError, match="no reply left"):
        llm_client.call_llm("m", "p")


def test_the_fake_can_raise_an_error(fake_llm):
    fake_llm.error = llm_module.LLMError("down")
    with pytest.raises(llm_module.LLMError, match="down"):
        llm_client.call_llm("m", "p")


def test_the_real_function_is_back_without_the_fixture(monkeypatch):
    assert llm_client.call_llm.__module__ == "p1.core.llm"
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(llm_module.LLMError):
        llm_client.call_llm("m", "p")
