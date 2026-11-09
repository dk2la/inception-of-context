from p2 import ask

# --- POST /ask ---


def test_ask_returns_the_answer_and_says_the_model_was_used(client, fake_llm):
    fake_llm.replies = ["Use Calculator.divide."]
    response = client.post("/ask", json={"question": "How do I divide?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Use Calculator.divide."
    assert response.json()["used_llm"] is True


def test_ask_returns_the_chunks_used_as_sources(client, fake_llm):
    fake_llm.replies = ["ok"]
    sources = client.post("/ask", json={"question": "How do I divide?"}).json()["sources"]
    assert sources
    for source in sources:
        assert {"path", "start_line", "end_line", "name", "text"} <= set(source)


def test_ask_respects_k(client, fake_llm):
    fake_llm.replies = ["ok"]
    sources = client.post("/ask", json={"question": "How do I divide?", "k": 2}).json()["sources"]
    assert len(sources) == 2


def test_ask_k_defaults_to_five(client, fake_llm):
    fake_llm.replies = ["ok"]
    sources = client.post("/ask", json={"question": "How do I divide?"}).json()["sources"]
    assert len(sources) == 5


def test_ask_without_a_question_is_a_422(client, fake_llm):
    assert client.post("/ask", json={}).status_code == 422


# --- Ollama is down ---


def test_ask_is_a_503_with_the_message_when_the_model_is_unreachable(client, fake_llm):
    fake_llm.error = ask.LLMError("Ollama is not reachable at http://x")
    response = client.post("/ask", json={"question": "How does divide work?"})
    assert response.status_code == 503
    assert "Ollama is not reachable" in response.json()["detail"]


def test_other_routes_keep_working_when_the_model_is_unreachable(client, fake_llm):
    fake_llm.error = ask.LLMError("Ollama is not reachable at http://x")
    client.post("/ask", json={"question": "How does divide work?"})
    assert client.get("/status").status_code == 200
    assert client.post("/context", json={"query": "divide"}).status_code == 200


def test_ask_is_a_503_when_nothing_listens_on_the_ollama_address(client, monkeypatch):
    monkeypatch.setattr(ask, "OLLAMA_HOST", "http://127.0.0.1:9")  # port 9 refuses at once
    response = client.post("/ask", json={"question": "How does divide work?"})
    assert response.status_code == 503
    assert "127.0.0.1:9" in response.json()["detail"]
