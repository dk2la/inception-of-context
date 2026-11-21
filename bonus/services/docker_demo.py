"""The Docker log watch demo, started from the dashboard: the same thing `make crash` does."""
import os
import socket
import subprocess

from p1.config.settings import settings
from p1.repositories.file_repository import file_repository
from p3.repositories.target_files import target_files_repository

DEMO_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "demo", "calculator_job.py")
DEMO_NAME = "calculator"
DEMO_IMAGE = "python:3.12-slim"
NO_SOCKET = ("the server cannot reach Docker from its container: restart it with make up-watch "
             "(it mounts the Docker or Podman socket; make up does not)")


def daemon_unreachable(text):
    """True when docker failed because there is no daemon behind the socket, not for another reason."""
    # debug: "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
    #   -> True (make up: no socket in the container). "Error: No such object: 30311b75d3f9" -> False
    text = text.lower()
    return "cannot connect to the docker daemon" in text or "docker.sock: connect: permission denied" in text


class DockerDemoService:
    def __init__(self, settings, script_path, file_repository, target_files_repository):
        # debug: script_path is bonus/demo/calculator_job.py. Its text is passed with python -c, so nothing but
        # target/ is mounted into the demo container (not the Docker socket, not the Index).
        # saved is the Target Project before the first demo run ({path: bytes}), or None: Reset demo restores it.
        self.settings = settings
        self.script_path = script_path
        self.file_repository = file_repository
        self.target_files_repository = target_files_repository
        self.saved = None

    def current_paths(self):
        return [self.file_repository.relative_path(path)
                for path in self.file_repository.list_files(self.settings.TARGET_DIR)]

    def save_target(self):
        """Remember target/ before the demo, once: a later run (after the fix) must not overwrite it."""
        # debug: first Start demo crash: saved == {"calculator/core.py": b"class Calculator:...", ...}
        if self.saved is None:
            self.saved = self.target_files_repository.take_snapshot(self.current_paths())

    def reset(self):
        """Put target/ back as it was before the demo: the fix is undone, files the Patch created are removed."""
        # debug: after a green fix, core.py has power and tests/test_power.py exists.
        # return == {"ok": True, "restored": ["calculator/core.py", ...], "removed": ["tests/test_power.py"]}
        # never started: return["ok"] == False
        if self.saved is None:
            return {"ok": False, "restored": [], "removed": [], "error": "nothing to reset: the demo has not run"}
        snapshot = dict(self.saved)
        removed = [path for path in self.current_paths() if path not in snapshot]
        for path in removed:
            snapshot[path] = None  # restore_snapshot deletes a file whose saved bytes are None
        current = self.target_files_repository.take_snapshot(list(self.saved))
        restored = [path for path, data in self.saved.items() if current[path] != data]
        self.target_files_repository.restore_snapshot(snapshot)
        self.saved = None
        return {"ok": True, "restored": restored, "removed": removed, "error": None}

    def run_docker(self, args):
        # debug: args == ["inspect", "30311b75d3f9", "--format", "..."] -> a CompletedProcess
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)

    def host_target_dir(self):
        """Where the Target Project is on the host. The server runs in a container and only knows its own path."""
        # debug: this container's hostname is its id, e.g. "30311b75d3f9". Its mount on /workspace has
        # Source "/Users/me/inception-of-context/target" -> that is returned.
        # not in a container (no such id), or no mount there: return == None
        fmt = '{{range .Mounts}}{{if eq .Destination "' + self.settings.TARGET_DIR + '"}}{{.Source}}{{end}}{{end}}'
        done = self.run_docker(["inspect", socket.gethostname(), "--format", fmt])
        if daemon_unreachable(done.stderr):
            raise ConnectionError(NO_SOCKET)
        source = done.stdout.strip()
        return source if done.returncode == 0 and source else None

    def start(self):
        """Replace container "calculator" with a fresh run of the demo job list. Return immediately."""
        # debug: return == {"ok": True, "service": "calculator", "error": None}
        # its log: four jobs, then the AttributeError traceback of Calculator.power
        # no docker CLI or not in a container: return["ok"] == False with the reason
        try:
            target = self.host_target_dir()
        except ConnectionError as error:
            return {"ok": False, "service": DEMO_NAME, "error": str(error)}
        except (OSError, subprocess.SubprocessError) as error:
            return {"ok": False, "service": DEMO_NAME, "error": f"docker is not usable here: {error}"}
        if target is None:
            return {"ok": False, "service": DEMO_NAME,
                    "error": "cannot find where target/ is on the host: run the server in Docker, or use make crash"}
        self.save_target()
        with open(self.script_path, encoding="utf-8") as handle:
            code = handle.read()
        self.run_docker(["rm", "-f", DEMO_NAME])
        done = self.run_docker([
            "run", "-d", "--name", DEMO_NAME, "-v", f"{target}:/workspace:ro", "-w", "/workspace",
            "-e", "PYTHONPATH=/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1", DEMO_IMAGE, "python", "-c", code])
        if done.returncode != 0:
            return {"ok": False, "service": DEMO_NAME, "error": done.stderr.strip()[-300:] or "docker run failed"}
        return {"ok": True, "service": DEMO_NAME, "error": None}


docker_demo_service = DockerDemoService(settings, os.path.normpath(DEMO_SCRIPT), file_repository,
                                        target_files_repository)
