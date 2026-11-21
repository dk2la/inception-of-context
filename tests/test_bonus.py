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
    fake_llm.replies = [json.dumps({
        "summary": "return 2",
        "files": [{"path": "a.py", "op": "modify", "content": new}],
    })]
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
    result = git_commit_service.commit_patch({
        "summary": "return 2",
        "files": [{"path": "a.py", "op": "modify", "content": "x"}],
    })
    assert result["ok"] is True
    assert result["message"] == "return two from a"
    log = subprocess.run(
        ["git", "-C", temp_index, "log", "-1", "--format=%s"],
        check=True, capture_output=True, text=True)
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
    monkeypatch.setattr(
        docker_watch_service.patch_bonus, "run",
        lambda *args, **kwargs: calls.append(kwargs) or {"status": "failed"})

    class Logs:
        stdout = iter(["ready\n", "Traceback (most recent call last):\n", "later\n"])

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bonus.services.docker_watch.subprocess.Popen", lambda *args, **kwargs: Logs())
    docker_watch_service.follow("web", "fix the crash")
    assert calls == [{"k": 5, "max_attempts": 3, "dry_run": False, "git_commit": False}]


CRASH_LOG = [
    "job subtract(9, 12) = -3.0\n",
    "Traceback (most recent call last):\n",
    '  File "/demo/job.py", line 18, in <module>\n',
    "    print(getattr(calculator, name)(a, b))\n",
    "AttributeError: 'Calculator' object has no attribute 'power'\n",
    "never read\n",
]


def test_the_watch_streams_every_line_and_sends_the_whole_traceback(monkeypatch):
    from bonus.repositories.event_repository import bonus_event_repository
    from bonus.services.docker_watch import docker_watch_service
    monkeypatch.setattr(bonus_event_repository, "events", [])
    calls = []
    monkeypatch.setattr(docker_watch_service.patch_bonus, "run", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr("bonus.services.docker_watch.subprocess.Popen", lambda *args, **kwargs: fake_logs(CRASH_LOG))
    docker_watch_service.follow("calculator", "fix it")
    logged = [e["detail"]["line"] for e in bonus_event_repository.events if e["type"] == "docker_log"]
    assert logged == [line.rstrip("\n") for line in CRASH_LOG[:5]]
    crash = [e["detail"] for e in bonus_event_repository.events if e["type"] == "docker_crash"][0]
    assert crash["line"] == "AttributeError: 'Calculator' object has no attribute 'power'"
    assert crash["traceback"].startswith("Traceback (most recent call last):")
    intent = calls[0][0]
    assert intent.startswith("fix it\n\nThe container calculator crashed.")
    assert "has no attribute 'power'" in intent


def test_a_log_that_ends_inside_a_traceback_still_runs_the_patch_loop(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    calls = []
    monkeypatch.setattr(docker_watch_service.patch_bonus, "run", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr("bonus.services.docker_watch.subprocess.Popen",
                        lambda *args, **kwargs: fake_logs(CRASH_LOG[1:3]))
    docker_watch_service.follow("calculator", "fix it")
    assert len(calls) == 1
    assert 'File "/demo/job.py"' in calls[0][0]


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
    assert script.headers["cache-control"] == "no-cache"
    assert script.status_code == 200
    assert "dry run" in script.text


class Completed:
    def __init__(self, code, out="", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def git_repo(root):
    subprocess.run(["git", "-C", root, "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "bonus@example.com"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "bonus"], check=True)


def test_dry_run_refuses_a_patch_that_empties_a_file(temp_index, fake_llm):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    fake_llm.replies = [json.dumps({"summary": "empty", "files": [{"path": "a.py", "op": "modify", "content": ""}]})]
    body = bonus_client(temp_index).post("/bonus/patch", json={"intent": "empty it", "dry_run": True}).json()
    assert body["status"] == "refused"
    assert body["diffs"][0]["op"] == "modify"
    assert "patch would empty a.py" in body["attempts"][0]["error"]


def test_dry_run_diffs_a_delete_and_a_new_file(temp_index, fake_llm):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    new = "x = 1\n"
    fake_llm.replies = [json.dumps({"summary": "replace", "files": [
        {"path": "a.py", "op": "delete"},
        {"path": "new.py", "op": "create", "content": new},
    ]})]
    body = bonus_client(temp_index).post("/bonus/patch", json={"intent": "replace a", "dry_run": True}).json()
    assert body["status"] == "dry_run"
    assert body["diffs"][0]["op"] == "delete"
    assert "-def a():" in body["diffs"][0]["diff"]
    assert "+x = 1" in body["diffs"][1]["diff"]
    assert os.path.exists(os.path.join(temp_index, "a.py"))
    assert not os.path.exists(os.path.join(temp_index, "new.py"))


def test_a_green_patch_is_committed_with_its_diff(temp_index, fake_llm, monkeypatch):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    write(temp_index, "old.py", "old = 1\n")
    with open(os.path.join(temp_index, "bin.dat"), "wb") as handle:
        handle.write(b"\x00\x01")
    git_repo(temp_index)
    fake_llm.replies = ["make a return two"]
    patch = {"summary": "return 2", "files": [
        {"path": "a.py", "op": "modify", "content": "def a():\n    return 2\n"},
        {"path": "new.py", "op": "create", "content": "x = 1\n"},
        {"path": "old.py", "op": "delete", "content": ""},
    ]}

    def run_attempt(intent, k, previous, number):
        from p3.models.patch import attempt_factory
        write(temp_index, "new.py", "x = 1\n")
        attempt = attempt_factory.new_attempt(number)
        attempt["ok"] = True
        attempt["validation"] = {"ok": True, "log": ""}
        attempt["patch"] = patch
        return attempt

    from p3.services.patch_loop import patch_loop_service
    monkeypatch.setattr(patch_loop_service, "run_attempt", run_attempt)
    body = bonus_client(temp_index).post("/bonus/patch", json={"intent": "return 2", "max_attempts": 1}).json()
    assert body["status"] == "success"
    assert body["dry_run"] is False
    assert body["git"]["ok"] is True
    assert body["git"]["message"] == "make a return two"
    ops = {item["path"]: item["op"] for item in body["diffs"]}
    assert ops == {"a.py": "modify", "new.py": "create", "old.py": "delete"}
    assert "+    return 2" in body["diffs"][0]["diff"]


def test_a_failed_attempt_is_retried_and_a_green_one_skips_git(temp_index, monkeypatch):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    seen = []

    def run_attempt(intent, k, previous, number):
        from p3.models.patch import attempt_factory
        seen.append(previous)
        attempt = attempt_factory.new_attempt(number)
        if number == 1:
            attempt["error"] = "validation failed"
            attempt["validation"] = {"ok": False, "log": "no"}
            attempt["patch"] = {"summary": "bad", "files": [{"path": "a.py", "op": "modify", "content": "x = 1\n"}]}
            return attempt
        attempt["ok"] = True
        attempt["validation"] = {"ok": True, "log": ""}
        attempt["patch"] = {"summary": "ok", "files": [{"path": "a.py", "op": "modify", "content": "x = 2\n"}]}
        return attempt

    from p3.services.patch_loop import patch_loop_service
    from bonus.services.patch_bonus import patch_bonus_service
    monkeypatch.setattr(patch_loop_service, "run_attempt", run_attempt)
    body = patch_bonus_service.run("fix", k=1, max_attempts=3, git_commit=False)
    assert [item is None for item in seen] == [True, False]
    assert seen[1]["error"] == "validation failed"
    assert body["status"] == "success"
    assert body["git"] is None
    assert len(body["attempts"]) == 2


def test_the_loop_stops_at_the_attempt_limit(temp_index, monkeypatch):
    from p1.config.settings import settings
    from p3.models.patch import attempt_factory
    from p3.services.patch_loop import patch_loop_service
    from bonus.services.patch_bonus import patch_bonus_service
    numbers = []

    def run_attempt(intent, k, previous, number):
        numbers.append(number)
        attempt = attempt_factory.new_attempt(number)
        attempt["error"] = "no"
        attempt["patch"] = None
        return attempt

    monkeypatch.setattr(patch_loop_service, "run_attempt", run_attempt)
    body = patch_bonus_service.run("fix", max_attempts=99, git_commit=False)
    assert numbers == [1, 2, 3]
    assert body["status"] == "failed"
    assert body["patch"] is None
    assert body["diffs"] == []
    numbers.clear()
    patch_bonus_service.run("fix", max_attempts=0, git_commit=False)
    assert numbers == [1]
    assert settings.MAX_ATTEMPTS == 3


def test_commit_message_falls_back_to_the_summary(fake_llm):
    from bonus.services.git_commit import git_commit_service
    fake_llm.replies = ["", ""]
    assert git_commit_service.commit_message("s" * 80) == "s" * 72
    assert git_commit_service.commit_message("") == "apply validated patch"
    fake_llm.replies = ['"fix the calculator"', "x" * 90, "first line\nsecond"]
    assert git_commit_service.commit_message("summary") == "fix the calculator"
    assert git_commit_service.commit_message("summary") == "x" * 72
    assert git_commit_service.commit_message("summary") == "first line"


def test_git_rev_parse_failure_means_there_is_no_repository(monkeypatch):
    from bonus.services.git_commit import git_commit_service
    monkeypatch.setattr(git_commit_service, "run_git", lambda root, args: Completed(128, "", "not a repo"))
    assert git_commit_service.repository_root() is None


def test_git_commit_refuses_paths_outside_the_repository(temp_index):
    git_repo(temp_index)
    from bonus.services.git_commit import git_commit_service
    outside = git_commit_service.commit_patch({"summary": "x", "files": [{"path": "../outside.py", "op": "modify"}]})
    assert outside["ok"] is False
    assert "outside the git repository" in outside["error"]
    empty = git_commit_service.commit_patch({"files": []})
    assert empty["ok"] is False
    assert "outside the git repository" in empty["error"]


def test_git_add_and_commit_failures_are_reported(temp_index, fake_llm, monkeypatch):
    write(temp_index, "a.py", "def a():\n    return 1\n")
    git_repo(temp_index)
    from bonus.services.git_commit import git_commit_service
    real = git_commit_service.run_git
    patch = {"files": [{"path": "a.py", "op": "modify", "content": "x"}]}

    def fail_add(root, args):
        if args[0] == "add":
            return Completed(1, "", "denied")
        return real(root, args)

    monkeypatch.setattr(git_commit_service, "run_git", fail_add)
    fake_llm.replies = ["add failed"]
    added = git_commit_service.commit_patch(dict(patch, summary="s"))
    assert added["ok"] is False
    assert added["error"] == "denied"

    def fail_add_quietly(root, args):
        if args[0] == "add":
            return Completed(1, "", "  ")
        return real(root, args)

    monkeypatch.setattr(git_commit_service, "run_git", fail_add_quietly)
    fake_llm.replies = ["add failed"]
    quiet = git_commit_service.commit_patch({"files": patch["files"]})
    assert quiet["error"] == "git add failed"
    assert quiet["message"] == "add failed"

    def fail_commit(root, args):
        if args[0] == "commit":
            return Completed(1, "", "hook declined")
        return real(root, args)

    monkeypatch.setattr(git_commit_service, "run_git", fail_commit)
    fake_llm.replies = ["commit failed"]
    committed = git_commit_service.commit_patch(dict(patch, summary="s"))
    assert committed["error"] == "hook declined"

    def fail_commit_quietly(root, args):
        if args[0] == "commit":
            return Completed(1, "nothing to commit", "")
        return real(root, args)

    monkeypatch.setattr(git_commit_service, "run_git", fail_commit_quietly)
    fake_llm.replies = ["commit failed"]
    quiet_commit = git_commit_service.commit_patch(dict(patch, summary="s"))
    assert quiet_commit["error"] == "nothing to commit"


def reset_docker():
    from bonus.services.docker_watch import docker_watch_service
    docker_watch_service._stop = True
    if docker_watch_service._thread is not None:
        docker_watch_service._thread.join(timeout=2)
    docker_watch_service._stop = False
    docker_watch_service._thread = None
    docker_watch_service.status = {"running": False, "service": None, "error": None}
    return docker_watch_service


def fake_logs(lines, waits=None):
    pending = list(waits or [])

    class Logs:
        stdout = iter(lines)

        def terminate(self):
            pass

        def kill(self):
            pass

        def wait(self, timeout=None):
            if pending:
                action = pending.pop(0)
                if action == "timeout":
                    raise subprocess.TimeoutExpired("docker", timeout or 5)
            return 0

    return Logs()


def test_docker_watch_starts_once_and_can_be_stopped(monkeypatch):
    import threading
    import time
    service = reset_docker()
    monkeypatch.setattr("bonus.services.docker_watch.shutil.which", lambda name: "/usr/bin/docker")
    entered = threading.Event()

    def follow(name, intent):
        entered.set()
        while not service._stop:
            time.sleep(0.01)

    monkeypatch.setattr(service, "follow", follow)
    first = service.start("web", "fix the crash")
    assert entered.wait(1)
    assert first["ok"] is True
    assert first["running"] is True
    again = service.start("web", "again")
    assert again["ok"] is False
    assert "already running" in again["error"]
    stopped = service.stop()
    service._thread.join(timeout=2)
    assert stopped["running"] is False
    assert stopped["service"] == "web"


def test_docker_watch_replaces_a_finished_thread(monkeypatch):
    import threading
    service = reset_docker()
    finished = threading.Thread(target=lambda: None)
    finished.start()
    finished.join()
    service._thread = finished
    monkeypatch.setattr("bonus.services.docker_watch.shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(service, "follow", lambda service_name, intent: None)
    body = service.start("web", "fix")
    service._thread.join(timeout=2)
    assert body["ok"] is True


def test_a_clean_exit_does_not_run_the_patch_loop(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    calls = []
    monkeypatch.setattr(docker_watch_service.patch_bonus, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        "bonus.services.docker_watch.subprocess.Popen",
        lambda *args, **kwargs: fake_logs(["exited with code 0\n"]))
    docker_watch_service.follow("web", "fix")
    assert calls == []
    assert docker_watch_service.crashed("exited with code 1") is True
    assert docker_watch_service.crashed("all good") is False


def test_a_nonzero_exit_runs_the_patch_loop(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    calls = []
    monkeypatch.setattr(
        docker_watch_service.patch_bonus, "run",
        lambda *args, **kwargs: calls.append(kwargs) or {"status": "failed"})
    monkeypatch.setattr(
        "bonus.services.docker_watch.subprocess.Popen",
        lambda *args, **kwargs: fake_logs(["exited with code 1\n"]))
    docker_watch_service.follow("web", "fix")
    assert calls == [{"k": 5, "max_attempts": 3, "dry_run": False, "git_commit": False}]


def test_stopping_the_watch_ignores_the_next_log_line(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    calls = []
    docker_watch_service._stop = True
    monkeypatch.setattr(docker_watch_service.patch_bonus, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        "bonus.services.docker_watch.subprocess.Popen",
        lambda *args, **kwargs: fake_logs(["Traceback (most recent call last):\n"]))
    docker_watch_service.follow("web", "fix")
    assert calls == []
    docker_watch_service._stop = False


def test_a_log_process_that_will_not_die_is_killed(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    logs = fake_logs([], waits=["timeout"])
    monkeypatch.setattr("bonus.services.docker_watch.subprocess.Popen", lambda *args, **kwargs: logs)
    docker_watch_service.follow("web", "fix")
    assert docker_watch_service.status["running"] is False


def test_docker_routes_start_and_stop(monkeypatch):
    from bonus.app import app
    from bonus.services.docker_watch import docker_watch_service
    monkeypatch.setattr(docker_watch_service, "start", lambda service, intent: {
        "ok": True, "running": True, "service": service, "error": None,
    })
    monkeypatch.setattr(docker_watch_service, "stop", lambda: {"running": False, "service": "web", "error": None})
    client = TestClient(app)
    started = client.post("/bonus/docker/watch", json={"service": "web", "intent": "fix the crash"}).json()
    assert started["ok"] is True and started["service"] == "web"
    assert client.post("/bonus/docker/stop").json()["running"] is False


def test_the_event_stream_waits_for_the_next_one(monkeypatch):
    from bonus.repositories.event_repository import bonus_event_repository
    from bonus.views.events import bonus_events_view
    monkeypatch.setattr(bonus_event_repository, "events", [])
    monkeypatch.setattr("bonus.views.events.time.sleep", lambda seconds: None)
    bonus_event_repository.add("finished", {"status": "failed"})
    stream = bonus_events_view.event_stream()
    assert json.loads(next(stream)[len("data: "):])["type"] == "finished"
    assert next(stream) == ": waiting\n\n"
    assert next(stream) == ": waiting\n\n"
    assert bonus_events_view.stream().media_type == "text/event-stream"


def test_the_script_is_left_out_when_the_page_has_no_body_tag():
    import asyncio
    from fastapi.responses import HTMLResponse, PlainTextResponse
    from bonus.app import BonusApp
    from p3.app import app as mandatory

    bonus = BonusApp(mandatory)

    class Url:
        def __init__(self, path):
            self.path = path

    class Req:
        def __init__(self, path):
            self.url = Url(path)

    async def plain(request):
        return PlainTextResponse("plain")

    async def page(request):
        async def chunks():
            yield b"<html>no closing body</html>"

        response = HTMLResponse("")
        response.body_iterator = chunks()
        return response

    untouched = asyncio.run(bonus.inject_script(Req("/bonus/bonus.js"), plain))
    assert untouched.body == b"plain"
    rewritten = asyncio.run(bonus.inject_script(Req("/"), page))
    assert b"bonus.js" not in rewritten.body
    assert rewritten.status_code == 200


def test_the_mandatory_app_does_not_grow_bonus_routes():
    import pathlib
    import subprocess
    import sys
    root = pathlib.Path(__file__).parent.parent
    code = "from p3.app import app; print('/bonus/reindex' in app.openapi()['paths'])"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root)
    assert result.stdout.strip() == "False", result.stderr
