import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent


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
    assert "stylesheet" not in page
    assert "src=" not in page


def test_dashboard_puts_data_into_the_page_as_text_only(client):
    assert "innerHTML" not in client.get("/").text


def test_part_2_alone_has_no_patch_route():
    """The Patch Loop tab says "not available" when /patch is missing from the app's list of routes.

    Checked in a fresh process: importing p3 adds /patch to the same app object.
    """
    code = "from p2.app import app; print('/patch' in app.openapi()['paths'])"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.stdout.strip() == "False"
