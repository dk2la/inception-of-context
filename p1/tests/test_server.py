from fastapi.testclient import TestClient

from ioc_index.server import create_app


def test_endpoints(ctx):
    ctx.indexer.full_sync()
    client = TestClient(create_app(ctx, start=False))
    st = client.get("/status").json()
    assert st["chunks"] > 0 and st["features"] == ["index", "watch"]
    files = client.get("/files").json()["files"]
    assert any(f["path"] == "notes/service.py" and f["chunks"] >= 6 for f in files)
    f = client.get("/file", params={"path": "notes/service.py"}).json()
    assert f["chunks"][0]["start_line"] == 1
    assert client.get("/file", params={"path": "../../etc/passwd"}).status_code == 400
    assert client.get("/file", params={"path": "/etc/passwd"}).status_code == 400
    assert client.get("/file", params={"path": "nope.py"}).status_code == 404
    page = client.get("/chunks", params={"limit": 5, "offset": 0}).json()
    assert page["total"] == st["chunks"] and len(page["items"]) == 5
    only = client.get("/chunks", params={"path": "main.py"}).json()
    assert all(i["metadata"]["path"] == "main.py" for i in only["items"])
    html = client.get("/").text
    assert "/static/p1/overview.js" in html and "/static/p1/files.js" in html
