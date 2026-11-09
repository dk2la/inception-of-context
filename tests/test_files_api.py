import os

from p1 import index


def write(target, name, text):
    path = os.path.join(target, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


# --- GET /files ---


def test_files_lists_every_indexed_file_with_its_chunk_count(client):
    response = client.get("/files")
    assert response.status_code == 200
    counts = {item["path"]: item["chunks"] for item in response.json()}
    assert counts["calculator/core.py"] > 0
    assert "main.py" in counts


def test_files_are_sorted_by_path(client):
    paths = [item["path"] for item in client.get("/files").json()]
    assert paths == sorted(paths)


def test_files_chunk_counts_add_up_to_the_whole_index(client):
    total = sum(item["chunks"] for item in client.get("/files").json())
    assert total == index.get_collection().count()


def test_files_never_lists_skipped_paths(client, temp_index):
    write(temp_index, "__pycache__/x.py", "def x():\n    pass\n")
    write(temp_index, ".hidden.py", "def h():\n    pass\n")
    index.index_all()
    for item in client.get("/files").json():
        assert "__pycache__" not in item["path"]
        assert not item["path"].startswith(".")


def test_files_follows_the_index_when_a_file_is_added_and_deleted(client, temp_index):
    path = write(temp_index, "extra.md", "# One\ntext\n\n# Two\nmore text\n")
    index.reindex_file(path)  # what the Watcher does
    assert {"path": "extra.md", "chunks": 2} in client.get("/files").json()
    os.remove(path)
    index.reindex_file(path)
    assert "extra.md" not in [item["path"] for item in client.get("/files").json()]


def test_files_of_an_empty_index_is_an_empty_list(client):
    index.get_collection().delete(where={"path": {"$ne": ""}})
    assert client.get("/files").json() == []


# --- GET /file ---


def test_file_returns_the_content_and_sorted_chunk_boundaries(client, temp_index):
    response = client.get("/file", params={"path": "calculator/core.py"})
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "calculator/core.py"
    with open(os.path.join(temp_index, "calculator", "core.py")) as f:
        assert body["content"] == f.read()
    starts = [chunk["start_line"] for chunk in body["chunks"]]
    assert starts and starts == sorted(starts)
    add = [chunk for chunk in body["chunks"] if chunk["name"] == "Calculator.add"]
    assert len(add) == 1 and add[0]["kind"] == "method"
    assert set(add[0]) == {"start_line", "end_line", "name", "kind"}


def test_file_that_does_not_exist_is_404(client):
    assert client.get("/file", params={"path": "does_not_exist.py"}).status_code == 404


def test_file_outside_the_target_project_is_404(client, temp_index):
    write(os.path.dirname(temp_index), "secret.txt", "secret")  # a real file, just outside the Target Project
    for path in ["../secret.txt", "calculator/../../secret.txt", "/etc/passwd"]:
        assert client.get("/file", params={"path": path}).status_code == 404, path


def test_file_that_is_a_symlink_out_of_the_target_project_is_404(client, temp_index):
    outside = write(os.path.dirname(temp_index), "secret.txt", "secret")
    os.symlink(outside, os.path.join(temp_index, "link.txt"))
    assert client.get("/file", params={"path": "link.txt"}).status_code == 404


def test_file_with_a_path_that_needs_normalizing_returns_the_normalized_path(client):
    response = client.get("/file", params={"path": "calculator/../calculator/core.py"})
    assert response.status_code == 200
    assert response.json()["path"] == "calculator/core.py"


def test_file_that_is_skipped_or_binary_or_a_folder_is_404(client, temp_index):
    write(temp_index, ".hidden/config", "x = 1")
    write(temp_index, "calculator/core.py.ioc.tmp", "x = 1")
    with open(os.path.join(temp_index, "image.bin"), "wb") as f:
        f.write(b"\x00\x01\x02")
    for path in [".hidden/config", "calculator/core.py.ioc.tmp", "image.bin", "calculator", ""]:
        assert client.get("/file", params={"path": path}).status_code == 404, path


def test_file_without_a_path_parameter_is_422(client):
    assert client.get("/file").status_code == 422
