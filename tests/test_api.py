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
