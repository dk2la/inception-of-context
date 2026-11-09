def test_root_serves_the_dashboard_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Inception-of-Context" in response.text
