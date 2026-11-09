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
