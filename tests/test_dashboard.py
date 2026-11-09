def test_root_serves_the_dashboard_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Inception-of-Context" in response.text


def test_dashboard_has_the_five_tabs(client):
    page = client.get("/").text
    for tab in ["Overview", "Files", "ChromaDB Explorer", "Ask & Retrieve", "Patch Loop"]:
        assert tab in page


def test_dashboard_works_offline(client):
    page = client.get("/").text
    assert "http://" not in page
    assert "https://" not in page
    assert "<link" not in page
    assert "src=" not in page


def test_dashboard_puts_data_into_the_page_as_text_only(client):
    assert "innerHTML" not in client.get("/").text
