from p1.config import settings
from p1.core import database


def test_status_reports_real_values(client, temp_index):
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {
        "chunks": database.get_collection().count(),
        "target_dir": temp_index,
        "chroma_dir": settings.CHROMA_DIR,
        "embedding_model": "all-MiniLM-L6-v2",
        "answer_model": "qwen2.5:3b",
        "patch_model": "qwen2.5-coder:3b",
        "ollama_host": settings.OLLAMA_HOST,
    }
    assert response.json()["chunks"] > 0


def test_status_reads_its_values_at_request_time(client, monkeypatch):
    monkeypatch.setattr(settings, "TARGET_DIR", "/somewhere/else")
    monkeypatch.setattr(settings, "ANSWER_MODEL", "another-model")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://localhost:1234")
    body = client.get("/status").json()
    assert body["target_dir"] == "/somewhere/else"
    assert body["answer_model"] == "another-model"
    assert body["ollama_host"] == "http://localhost:1234"


def test_status_chunk_count_follows_the_index(client):
    before = client.get("/status").json()["chunks"]
    database.get_collection().delete(where={"path": "calculator/core.py"})
    assert client.get("/status").json()["chunks"] < before
