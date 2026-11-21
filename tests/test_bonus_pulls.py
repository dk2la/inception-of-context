"""The bonus pull request: checks first, then Merge applies exactly that Patch, or Close drops it."""
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bonus.repositories.pull_repository import pull_repository
from p3.services.patch_loop import patch_loop_service
from p3.services.validation import validation_service


POWER_METHOD = '''
    def power(self, a, b):
        """Return a ** b."""
        return float(a ** b)
'''


@pytest.fixture
def bonus(client, monkeypatch):
    """The bonus app over the indexed copy of the real Target Project, with no pull requests yet."""
    from bonus.app import app
    monkeypatch.setattr(pull_repository, "pulls", {})
    monkeypatch.setattr(pull_repository, "next_number", 1)
    return TestClient(app)


@pytest.fixture
def core(temp_index):
    return Path(temp_index) / "calculator" / "core.py"


def power_reply(core):
    return json.dumps({"summary": "add power", "files": [
        {"path": "calculator/core.py", "op": "modify", "content": core.read_text() + POWER_METHOD}]})


def broken_reply(core):
    return json.dumps({"summary": "break add", "files": [
        {"path": "calculator/core.py", "op": "modify", "content": core.read_text().replace("a + b", "a - b")}]})


def open_pull(bonus, core, fake_llm, **extra):
    fake_llm.replies = [power_reply(core)]
    body = {"intent": "add a power method", "k": 3, "max_attempts": 1, "pull_request": True, **extra}
    return bonus.post("/bonus/patch", json=body).json()


def test_a_green_patch_opens_a_pull_request_and_leaves_the_disk_alone(bonus, core, fake_llm):
    before = core.read_text()
    body = open_pull(bonus, core, fake_llm)
    assert body["status"] == "open"
    assert body["git"] is None
    pull = body["pull"]
    assert pull["number"] == 1
    assert pull["state"] == "open"
    assert pull["title"] == "add power"
    assert pull["checks"]["sanity"] is True and pull["checks"]["validation"] is True
    assert "base" not in pull
    assert "+    def power(self, a, b):" in pull["files"][0]["diff"]
    assert body["attempts"][0]["ok"] is True
    assert core.read_text() == before
    assert bonus.get("/bonus/pulls").json()[0]["number"] == 1


def test_a_failed_attempt_is_retried_before_the_pull_request_opens(bonus, core, fake_llm):
    before = core.read_text()
    fake_llm.replies = [broken_reply(core), power_reply(core)]
    body = bonus.post("/bonus/patch", json={"intent": "add power", "k": 3, "pull_request": True}).json()
    assert body["status"] == "open"
    assert body["pull"]["attempts"] == 2
    assert core.read_text() == before


def test_a_red_pull_request_run_opens_nothing(bonus, core, fake_llm):
    fake_llm.replies = [broken_reply(core)]
    body = bonus.post("/bonus/patch", json={"intent": "break", "k": 3, "max_attempts": 1, "pull_request": True})
    body = body.json()
    assert body["status"] == "failed"
    assert "pull" not in body
    assert bonus.get("/bonus/pulls").json() == []


def test_merge_applies_exactly_the_reviewed_patch(bonus, core, fake_llm):
    opened = open_pull(bonus, core, fake_llm)
    expected = opened["pull"]["patch"]["files"][0]["content"]
    body = bonus.post("/bonus/pulls/1/merge", json={"git_commit": False}).json()
    assert body["status"] == "success"
    assert body["git"] is None
    assert body["pull"]["state"] == "merged"
    assert body["pull"]["merge"]["git"] is None
    assert body["pull"]["merge"]["at"] > 0
    assert body["attempts"][0]["validation"]["ok"] is True
    assert core.read_text() == expected
    assert fake_llm.replies == []  # Merge does not ask the model again


def test_merge_commits_when_asked(bonus, core, fake_llm, temp_index):
    subprocess.run(["git", "-C", temp_index, "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", temp_index, "config", "user.email", "bonus@example.com"], check=True)
    subprocess.run(["git", "-C", temp_index, "config", "user.name", "bonus"], check=True)
    open_pull(bonus, core, fake_llm)
    fake_llm.replies = ["Add a power method"]
    body = bonus.post("/bonus/pulls/1/merge").json()
    assert body["status"] == "success"
    assert body["git"]["ok"] is True
    assert body["pull"]["merge"]["git"]["message"] == "Add a power method"


def test_merge_refuses_when_the_file_changed_since_the_review(bonus, core, fake_llm):
    open_pull(bonus, core, fake_llm)
    core.write_text(core.read_text() + "\n# edited by hand\n")
    edited = core.read_text()
    body = bonus.post("/bonus/pulls/1/merge", json={}).json()
    assert body["status"] == "conflict"
    assert "calculator/core.py" in body["error"]
    assert body["pull"]["state"] == "open"
    assert core.read_text() == edited


def test_merge_that_fails_validation_is_rolled_back_and_stays_open(bonus, core, fake_llm, monkeypatch):
    open_pull(bonus, core, fake_llm)
    before = core.read_text()
    monkeypatch.setattr(validation_service, "run_validation", lambda changed: (False, "1 failed"))
    body = bonus.post("/bonus/pulls/1/merge", json={"git_commit": False}).json()
    assert body["status"] == "failed"
    assert "1 failed" in body["error"]
    assert body["pull"]["state"] == "open"
    assert core.read_text() == before


def test_close_drops_the_pull_request_and_merge_then_refuses(bonus, core, fake_llm):
    before = core.read_text()
    open_pull(bonus, core, fake_llm)
    closed = bonus.post("/bonus/pulls/1/close").json()
    assert closed["state"] == "closed" and closed["closed_at"] > 0
    assert bonus.post("/bonus/pulls/1/close").json()["state"] == "closed"
    body = bonus.post("/bonus/pulls/1/merge", json={}).json()
    assert body["status"] == "refused"
    assert body["error"] == "pull request #1 is closed"
    assert core.read_text() == before


def test_an_unknown_pull_request_is_a_404(bonus):
    assert bonus.post("/bonus/pulls/99/merge", json={}).status_code == 404
    assert bonus.post("/bonus/pulls/99/close").status_code == 404


def test_pull_requests_are_listed_newest_first(bonus, core, fake_llm):
    open_pull(bonus, core, fake_llm)
    open_pull(bonus, core, fake_llm)
    assert [pull["number"] for pull in bonus.get("/bonus/pulls").json()] == [2, 1]


def test_a_pull_request_title_falls_back_to_the_intent(bonus, core, fake_llm):
    fake_llm.replies = [json.dumps({"files": [
        {"path": "calculator/core.py", "op": "modify", "content": core.read_text() + POWER_METHOD}]})]
    body = bonus.post("/bonus/patch", json={"intent": "add power", "k": 3, "max_attempts": 1, "pull_request": True})
    body = body.json()
    assert body["pull"]["title"] == "add power"


def test_keep_false_rolls_back_a_green_attempt(client, core, fake_llm):
    before = core.read_text()
    fake_llm.replies = [power_reply(core)]
    attempt = patch_loop_service.run_attempt("add power", 3, None, 1, keep=False)
    assert attempt["ok"] is True
    assert attempt["error"] is None
    assert core.read_text() == before


# --- the history is saved next to the Index and read back after a restart ---


def test_pull_requests_survive_a_restart(bonus, core, fake_llm):
    open_pull(bonus, core, fake_llm)
    bonus.post("/bonus/pulls/1/merge", json={"git_commit": False})
    open_pull(bonus, core, fake_llm)
    pull_repository.loaded_from = None  # what a new process sees
    pull_repository.pulls = {}
    pulls = bonus.get("/bonus/pulls").json()
    assert [(p["number"], p["state"]) for p in pulls] == [(2, "open"), (1, "merged")]
    assert "+    def power(self, a, b):" in pulls[1]["files"][0]["diff"]
    assert pull_repository.get(2)["base"]["calculator/core.py"] == core.read_bytes()
    assert pull_repository.next_number == 3


def test_a_broken_history_file_means_no_history(temp_index, monkeypatch):
    from p1.config.settings import settings
    import os
    monkeypatch.setattr(pull_repository, "loaded_from", None)
    os.makedirs(os.path.dirname(pull_repository.path()), exist_ok=True)
    with open(pull_repository.path(), "w") as handle:
        handle.write("not json")
    assert pull_repository.all() == []
    assert settings.CHROMA_DIR in pull_repository.path()


def test_a_base_of_a_new_file_is_kept_as_none(temp_index, monkeypatch):
    monkeypatch.setattr(pull_repository, "loaded_from", None)
    pull_repository.add({"title": "t", "state": "open", "base": {"new.py": None}})
    pull_repository.loaded_from = None
    assert pull_repository.get(1)["base"] == {"new.py": None}


def test_an_unwritable_history_only_loses_the_history(temp_index, monkeypatch):
    monkeypatch.setattr(pull_repository, "loaded_from", None)
    monkeypatch.setattr(pull_repository, "path", lambda: "/proc/no/such/bonus_pulls.json")
    assert pull_repository.add({"title": "t", "state": "open", "base": {}})["number"] == 1
