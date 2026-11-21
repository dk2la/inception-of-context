"""The bonus routes: reindex, dry-run diff, git commit, docker watch, live events."""
import json
import os
import subprocess

from fastapi.testclient import TestClient

from p1.services.indexer import indexer_service


def bonus_client(temp_index):
    from bonus.app import app
    indexer_service.index_all()
    return TestClient(app)


def write(root, name, text):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(name) else None
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_reindex_reports_the_chunk_count(temp_index):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    body = bonus_client(temp_index).post("/bonus/reindex").json()
    assert body["chunks"] >= 1


def test_dry_run_returns_a_diff_and_does_not_write(temp_index, fake_llm):
    path = write(temp_index, "a.py", "def a():\n    return 1\n")
    new = "def a():\n    return 2\n"
    fake_llm.replies = [json.dumps({"summary": "return 2", "files": [{"path": "a.py", "op": "modify", "content": new}]})]
    body = bonus_client(temp_index).post("/bonus/patch", json={"intent": "return 2", "dry_run": True, "k": 1}).json()
    assert body["status"] == "dry_run"
    assert body["dry_run"] is True
    assert body["diffs"][0]["path"] == "a.py"
    assert "-    return 1" in body["diffs"][0]["diff"]
    assert "+    return 2" in body["diffs"][0]["diff"]
    assert open(path, encoding="utf-8").read() == "def a():\n    return 1\n"


def test_dry_run_refuses_a_patch_that_is_not_json(temp_index, fake_llm):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    fake_llm.replies = ["not json"]
    body = bonus_client(temp_index).post("/bonus/patch", json={"intent": "break", "dry_run": True}).json()
    assert body["status"] == "refused"
    assert body["diffs"] == []
    assert body["attempts"][0]["generation"]["ok"] is False


def test_git_commit_records_the_model_message(temp_index, fake_llm):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    subprocess.run(["git", "-C", temp_index, "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", temp_index, "config", "user.email", "bonus@example.com"], check=True)
    subprocess.run(["git", "-C", temp_index, "config", "user.name", "bonus"], check=True)
    fake_llm.replies = ["return two from a"]
    from bonus.services.git_commit import git_commit_service
    result = git_commit_service.commit_patch({"summary": "return 2", "files": [{"path": "a.py", "op": "modify", "content": "x"}]})
    assert result["ok"] is True
    assert result["message"] == "return two from a"
    log = subprocess.run(["git", "-C", temp_index, "log", "-1", "--format=%s"], check=True, capture_output=True, text=True)
    assert log.stdout.strip() == "return two from a"


def test_git_commit_reports_when_there_is_no_repository(temp_index, fake_llm, monkeypatch):
    from bonus.services.git_commit import git_commit_service
    monkeypatch.setattr(git_commit_service, "repository_root", lambda: None)
    result = git_commit_service.commit_patch({"summary": "x", "files": [{"path": "a.py"}]})
    assert result["ok"] is False
    assert "not inside a git repository" in result["error"]


def test_docker_watch_refuses_when_the_cli_is_missing(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    monkeypatch.setattr("bonus.services.docker_watch.shutil.which", lambda name: None)
    body = docker_watch_service.start("web", "fix the crash")
    assert body["ok"] is False
    assert "docker CLI" in body["error"]


def test_a_traceback_in_the_logs_runs_one_patch_loop(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    calls = []
    monkeypatch.setattr(docker_watch_service.patch_bonus, "run", lambda *args, **kwargs: calls.append(kwargs) or {"status": "failed"})

    class Logs:
        stdout = iter(["ready\n", "Traceback (most recent call last):\n", "later\n"])

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bonus.services.docker_watch.subprocess.Popen", lambda *args, **kwargs: Logs())
    docker_watch_service.follow("web", "fix the crash")
    assert calls == [{"k": 5, "max_attempts": 1, "dry_run": False, "git_commit": False}]


def test_bonus_events_stream_the_validation_status(monkeypatch):
    from bonus.repositories.event_repository import bonus_event_repository
    from bonus.views.events import bonus_events_view
    monkeypatch.setattr(bonus_event_repository, "events", [])
    bonus_event_repository.add("attempt", {"number": 1, "ok": False, "validation_ok": False})
    message = next(bonus_events_view.event_stream())
    assert message.startswith("data: ")
    assert json.loads(message[len("data: "):])["detail"]["validation_ok"] is False


def test_the_bonus_dashboard_page_loads_the_script(temp_index):
    page = bonus_client(temp_index).get("/").text
    assert '<script src="/bonus/bonus.js"></script>' in page
    script = bonus_client(temp_index).get("/bonus/bonus.js")
    assert script.status_code == 200
    assert "dry run" in script.text


def test_the_mandatory_app_does_not_grow_bonus_routes():
    import pathlib
    import subprocess
    import sys
    root = pathlib.Path(__file__).parent.parent
    code = "from p3.app import app; print('/bonus/reindex' in app.openapi()['paths'])"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root)
    assert result.stdout.strip() == "False", result.stderr
