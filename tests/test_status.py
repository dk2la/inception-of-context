from p1 import index
from p2 import ask


def test_status_reports_real_values(client, temp_index):
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {
        "chunks": index.get_collection().count(),
        "target_dir": temp_index,
        "chroma_dir": index.CHROMA_DIR,
        "answer_model": "qwen2.5:3b",
        "patch_model": "qwen2.5-coder:3b",
        "ollama_host": ask.OLLAMA_HOST,
    }
    assert response.json()["chunks"] > 0


def test_status_reads_its_values_at_request_time(client, monkeypatch):
    monkeypatch.setattr(index, "TARGET_DIR", "/somewhere/else")
    monkeypatch.setattr(ask, "ANSWER_MODEL", "another-model")
    monkeypatch.setattr(ask, "OLLAMA_HOST", "http://localhost:1234")
    body = client.get("/status").json()
    assert body["target_dir"] == "/somewhere/else"
    assert body["answer_model"] == "another-model"
    assert body["ollama_host"] == "http://localhost:1234"


def test_status_chunk_count_follows_the_index(client):
    before = client.get("/status").json()["chunks"]
    index.get_collection().delete(where={"path": "calculator/core.py"})
    assert client.get("/status").json()["chunks"] < before
