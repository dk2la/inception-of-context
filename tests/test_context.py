def test_context_returns_the_k_best_chunks(client):
    response = client.post("/context", json={"query": "divide", "k": 3})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3


def test_context_finds_the_divide_method(client):
    results = client.post("/context", json={"query": "divide", "k": 3}).json()["results"]
    assert "Calculator.divide" in [r["name"] for r in results]


def test_context_results_carry_similarity_and_score(client):
    results = client.post("/context", json={"query": "divide", "k": 3}).json()["results"]
    for result in results:
        assert {"path", "start_line", "end_line", "name", "kind", "text", "similarity", "score"} <= set(result)


def test_context_k_defaults_to_five(client):
    results = client.post("/context", json={"query": "divide"}).json()["results"]
    assert len(results) <= 5


def test_context_without_a_query_is_a_422(client):
    assert client.post("/context", json={}).status_code == 422
