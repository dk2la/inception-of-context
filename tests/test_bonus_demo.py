"""POST /bonus/docker/demo: the make crash button, run by the server from inside its container."""
from fastapi.testclient import TestClient

from bonus.services.docker_demo import docker_demo_service


class Done:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def scripted(monkeypatch, replies):
    """docker answers from a list, in order; every command is recorded."""
    calls = []

    def run_docker(args):
        calls.append(args)
        return replies.pop(0)

    monkeypatch.setattr(docker_demo_service, "run_docker", run_docker)
    return calls


def test_the_demo_mounts_the_host_target_and_runs_the_job_list(monkeypatch):
    calls = scripted(monkeypatch, [Done(out="/home/me/ioc/target\n"), Done(), Done(out="abc\n")])
    assert docker_demo_service.start() == {"ok": True, "service": "calculator", "error": None}
    assert calls[0][0] == "inspect"
    assert calls[1] == ["rm", "-f", "calculator"]
    run = calls[2]
    assert run[:4] == ["run", "-d", "--name", "calculator"]
    assert "/home/me/ioc/target:/workspace:ro" in run
    assert "/var/run/docker.sock" not in " ".join(run)
    assert "getattr(calculator, name)" in run[-1]  # bonus/demo/calculator_job.py, passed as python -c


def test_outside_a_container_the_demo_says_to_use_make_crash(monkeypatch):
    scripted(monkeypatch, [Done(code=1, err="No such object")])
    body = docker_demo_service.start()
    assert body["ok"] is False and "make crash" in body["error"]


def test_a_missing_docker_cli_is_reported(monkeypatch):
    def run_docker(args):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(docker_demo_service, "run_docker", run_docker)
    body = docker_demo_service.start()
    assert body["ok"] is False and "not usable" in body["error"]


def test_a_failed_docker_run_is_reported(monkeypatch):
    scripted(monkeypatch, [Done(out="/t\n"), Done(), Done(code=125, err="Unable to find image")])
    assert docker_demo_service.start()["error"] == "Unable to find image"
    scripted(monkeypatch, [Done(out="/t\n"), Done(), Done(code=125)])
    assert docker_demo_service.start()["error"] == "docker run failed"


def test_run_docker_calls_the_docker_cli(monkeypatch):
    seen = []
    monkeypatch.setattr("bonus.services.docker_demo.subprocess.run", lambda cmd, **kwargs: seen.append(cmd) or Done())
    docker_demo_service.run_docker(["ps"])
    assert seen == [["docker", "ps"]]


def test_the_demo_route(monkeypatch):
    from bonus.app import app
    monkeypatch.setattr(docker_demo_service, "start", lambda: {"ok": True, "service": "calculator", "error": None})
    assert TestClient(app).post("/bonus/docker/demo").json()["ok"] is True


# --- Reset demo: target/ as it was before the first run ---


def test_reset_undoes_the_fix_and_removes_new_files(temp_index, monkeypatch):
    import os
    core = os.path.join(temp_index, "calculator", "core.py")
    os.makedirs(os.path.dirname(core))
    with open(core, "w") as handle:
        handle.write("class Calculator:\n    pass\n")
    monkeypatch.setattr(docker_demo_service, "saved", None)
    assert docker_demo_service.reset()["ok"] is False  # never started
    docker_demo_service.save_target()
    docker_demo_service.save_target()  # a second run keeps the first copy
    with open(core, "w") as handle:
        handle.write("class Calculator:\n    def power(self, a, b):\n        return a ** b\n")
    with open(os.path.join(temp_index, "calculator", "test_power.py"), "w") as handle:
        handle.write("x = 1\n")
    body = docker_demo_service.reset()
    assert body == {"ok": True, "restored": ["calculator/core.py"], "removed": ["calculator/test_power.py"],
                    "error": None}
    assert open(core).read() == "class Calculator:\n    pass\n"
    assert not os.path.exists(os.path.join(temp_index, "calculator", "test_power.py"))
    assert docker_demo_service.saved is None


def test_the_reset_route(monkeypatch):
    from bonus.app import app
    monkeypatch.setattr(docker_demo_service, "reset",
                        lambda: {"ok": True, "restored": [], "removed": [], "error": None})
    assert TestClient(app).post("/bonus/docker/demo/reset").json()["ok"] is True


# --- after a green fix, the watch runs the container again ---


class Rerun:
    def __init__(self, lines, code=0, hang=False):
        self.stdout = iter(lines)
        self.code, self.hang = code, hang

    def wait(self, timeout=None):
        import subprocess
        if self.hang:
            raise subprocess.TimeoutExpired("docker", timeout)
        return self.code

    def kill(self):
        pass


def events_of(kind):
    from bonus.repositories.event_repository import bonus_event_repository
    return [e["detail"] for e in bonus_event_repository.events if e["type"] == kind]


def rerun(monkeypatch, proc):
    from bonus.repositories.event_repository import bonus_event_repository
    from bonus.services.docker_watch import docker_watch_service
    monkeypatch.setattr(bonus_event_repository, "events", [])
    seen = []
    monkeypatch.setattr("bonus.services.docker_watch.subprocess.Popen",
                        lambda cmd, **kwargs: seen.append(cmd) or proc)
    docker_watch_service.verify("calculator")
    return seen


def test_a_clean_rerun_is_verified(monkeypatch):
    seen = rerun(monkeypatch, Rerun(["job power(2, 8) = 256.0\n", "all jobs done\n"]))
    assert seen == [["docker", "start", "-a", "calculator"]]
    assert [e["line"] for e in events_of("docker_log")] == ["job power(2, 8) = 256.0", "all jobs done"]
    assert events_of("docker_verified") == [{"service": "calculator", "ok": True, "exit_code": 0}]


def test_a_rerun_that_crashes_again_is_not_verified(monkeypatch):
    rerun(monkeypatch, Rerun(["Traceback (most recent call last):\n", "ValueError: x\n"], code=1))
    assert events_of("docker_verified")[0]["ok"] is False


def test_a_rerun_that_never_ends_is_not_verified(monkeypatch):
    rerun(monkeypatch, Rerun(["serving\n"], hang=True))
    assert events_of("docker_verified") == [{"service": "calculator", "ok": False, "exit_code": None}]


def test_only_a_green_fix_is_verified(monkeypatch):
    from bonus.services.docker_watch import docker_watch_service
    verified = []
    monkeypatch.setattr(docker_watch_service, "verify", verified.append)
    for status in ("failed", "success"):
        monkeypatch.setattr(docker_watch_service.patch_bonus, "run", lambda *a, status=status, **k: {"status": status})
        docker_watch_service.patch_after_crash("calculator", "fix", ["Traceback", "AttributeError: x"])
    assert verified == ["calculator"]
