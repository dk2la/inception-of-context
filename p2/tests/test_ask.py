import pytest
from fastapi.testclient import TestClient

from ioc_api.ask import classify, code_identifiers
from ioc_api.llm import ScriptedLLM
from ioc_api.server import attach_services, create_app


@pytest.mark.parametrize("q,expected", [
    ("is there a function called authenticate?", ("exists", "authenticate")),
    ("Is there a method `NoteService.archive`?", ("exists", "NoteService.archive")),
    ("does greet exist?", ("exists", "greet")),
    ("есть ли функция whisper?", ("exists", "whisper")),
    ("what functions are in notes/service.py?", ("list_file", "notes/service.py")),
    ("which methods exist in the file storage.py", ("list_file", "storage.py")),
    ("какие функции в файле main.py?", ("list_file", "main.py")),
    ("where is greet defined?", ("where_defined", "greet")),
    ("where is authenticate used?", ("where_used", "authenticate")),
    ("где используется greet", ("where_used", "greet")),
    ("explain how search works", None),
])
def test_classify(q, expected):
    assert classify(q) == expected


def test_code_identifiers():
    assert set(code_identifiers("what does the authenticate function do with user_id and NoteService.find()?")) == \
        {"NoteService.find", "user_id", "authenticate"}
    assert code_identifiers("what does main.py do?") == []


@pytest.fixture
def client(ctx):
    ctx.indexer.full_sync()
    llm = ScriptedLLM()
    attach_services(ctx, llm=llm)
    return TestClient(create_app(ctx, start=False)), llm


def test_symbol_questions_never_reach_the_model(client):
    c, llm = client
    d = c.post("/ask", json={"question": "is there a function called authenticate?"}).json()
    assert d["mode"] == "symbol:exists" and d["answer"].startswith("No.")
    d = c.post("/ask", json={"question": "Is there a method search?"}).json()
    assert d["answer"].startswith("Yes.") and "notes/service.py:26" in d["answer"]
    d = c.post("/ask", json={"question": "what functions are in notes/service.py?"}).json()
    names = [s["qualname"] for s in d["facts"]["symbols"]]
    assert names == ["NoteService", "NoteService.__init__", "NoteService.create", "NoteService.find",
                     "NoteService.search", "NoteService.by_tag", "NoteService.remove"]
    d = c.post("/ask", json={"question": "what functions are in nothere.py?"}).json()
    assert d["facts"]["found"] is False and "no file" in d["answer"]
    assert llm.calls == []


def test_rag_injects_facts_and_flags_invented_names(client):
    c, llm = client
    llm.replies = ["It calls `self.storage.list_all()` and then `magic_filter()` at notes/service.py:26."]
    d = c.post("/ask", json={"question": "explain how NoteService.search works", "k": 3}).json()
    assert d["mode"] == "rag" and len(d["sources"]) == 3
    prompt = llm.calls[0]["messages"][-1]["content"]
    assert "FACTS:" in prompt and "NoteService.search` is a method" in prompt and "SNIPPETS:" in prompt
    assert d["unverified"] == ["magic_filter"]


def test_rag_states_missing_symbols_up_front(client):
    c, llm = client
    llm.replies = ["The indexed code does not show it."]
    d = c.post("/ask", json={"question": "what does the authenticate function do?"}).json()
    assert d["answer"].startswith("`authenticate` does not exist")
    assert "does NOT exist" in llm.calls[0]["messages"][-1]["content"]


def test_context_endpoint_and_validation(client):
    c, _ = client
    d = c.post("/context", json={"query": "case insensitive search", "k": 4}).json()
    assert d["count"] == 4 and d["chunks"][0]["score"] >= d["chunks"][-1]["score"]
    assert c.post("/context", json={"query": "", "k": 4}).status_code == 422
    assert c.post("/context", json={"query": "x", "k": 0}).status_code == 422
    assert c.post("/context", json={"query": "x", "k": 500}).status_code == 422
    assert c.post("/ask", json={"question": "   "}).status_code == 422


def test_llm_down_is_a_clean_503(ctx):
    ctx.indexer.full_sync()
    from ioc_api.llm import OllamaClient
    attach_services(ctx, llm=OllamaClient("http://127.0.0.1:9"))
    c = TestClient(create_app(ctx, start=False))
    r = c.post("/ask", json={"question": "explain the cli"})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]
    # symbol questions still work without a model
    assert c.post("/ask", json={"question": "is there a function greet?"}).status_code == 200
