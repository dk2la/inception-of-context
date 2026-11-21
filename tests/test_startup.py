import os
import threading
import time

from fastapi.testclient import TestClient

from p1.core.chroma_db import chroma_db
from p1.repositories.event_repository import event_repository
from p1.services.indexer import indexer_service
from p2.app import app, lifecycle


def wait_until(condition, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def write(target, name, text):
    with open(os.path.join(target, name), "w") as f:
        f.write(text)


def test_startup_indexes_the_target_project_and_then_stops_the_watcher(temp_index, monkeypatch):
    monkeypatch.setattr(event_repository, "events", [])
    write(temp_index, "a.py", "def a():\n    return 1\n")
    with TestClient(app):
        assert wait_until(lambda: chroma_db.get_collection().count() > 0)
        assert wait_until(lambda: lifecycle.observer is not None)  # the Watcher starts after the rescan
        observer = lifecycle.observer
        assert observer.is_alive()
        assert event_repository.events == []  # the rescan at startup is not a live change: no events
    assert not observer.is_alive()


def test_threads_asking_for_the_collection_at_the_same_time_share_one_client(temp_index):
    """The first request and the startup thread can both need the Index while it is being opened."""
    found = []
    threads = [threading.Thread(target=lambda: found.append(chroma_db.get_collection())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(found) == 8
    assert all(collection is found[0] for collection in found)


def test_after_startup_the_watcher_reindexes_changes(temp_index, monkeypatch):
    monkeypatch.setattr(event_repository, "events", [])
    with TestClient(app) as client:
        assert wait_until(lambda: lifecycle.observer is not None)
        write(temp_index, "new.py", "def new():\n    return 1\n")
        assert wait_until(lambda: any(e["path"] == "new.py" for e in event_repository.events))
        assert client.get("/status").status_code == 200


def test_the_server_answers_while_the_first_indexing_is_still_running(temp_index, monkeypatch):
    release = threading.Event()

    def slow_index_all():
        release.wait(5)
        return 0

    monkeypatch.setattr(indexer_service, "index_all", slow_index_all)
    try:
        with TestClient(app) as client:
            assert client.get("/status").status_code == 200
            assert lifecycle.observer is None  # still busy indexing
            release.set()
            assert wait_until(lambda: lifecycle.observer is not None)
    finally:
        release.set()


def test_a_failing_first_indexing_is_printed_and_the_server_keeps_running(temp_index, monkeypatch, capsys):
    def broken_index_all():
        raise RuntimeError("the Chroma folder is not writable")

    monkeypatch.setattr(indexer_service, "index_all", broken_index_all)
    with TestClient(app) as client:
        assert wait_until(lambda: "indexing failed" in capsys.readouterr().out)
        assert client.get("/status").status_code == 200
    assert lifecycle.observer is None


def test_the_watcher_and_the_api_share_one_chroma_client(temp_index, monkeypatch):
    import chromadb

    created = []
    real_client = chromadb.PersistentClient
    monkeypatch.setattr(chromadb, "PersistentClient", lambda path: created.append(path) or real_client(path=path))
    monkeypatch.setattr(event_repository, "events", [])
    with TestClient(app) as client:
        assert wait_until(lambda: lifecycle.observer is not None)
        write(temp_index, "new.py", "def new():\n    return 1\n")
        assert wait_until(lambda: any(e["path"] == "new.py" for e in event_repository.events))
        client.get("/status")
    assert len(created) == 1
