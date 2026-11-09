from fastapi.testclient import TestClient

from p3.app import app


def test_status_is_ok():
    response = TestClient(app).get("/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
