"""Watch one container's logs and run a single Patch Loop when it crashes."""
import shutil
import subprocess
import threading

from bonus.repositories.event_repository import bonus_event_repository
from bonus.services.patch_bonus import patch_bonus_service


class DockerWatchService:
    def __init__(self, events, patch_bonus):
        self.events = events
        self.patch_bonus = patch_bonus
        self._stop = False
        self._thread = None
        self.status = {"running": False, "service": None, "error": None}

    def start(self, service, intent):
        """Follow `docker logs -f service`. Return immediately. One crash runs the Patch Loop once."""
        if shutil.which("docker") is None:
            self.status = {"running": False, "service": service, "error": "docker CLI is not available"}
            return {"ok": False, **self.status}
        if self._thread and self._thread.is_alive():
            return {"ok": False, "running": True, "service": self.status["service"],
                    "error": "a docker watch is already running"}
        self._stop = False
        self.status = {"running": True, "service": service, "error": None}
        self._thread = threading.Thread(target=self.follow, args=(service, intent), daemon=True)
        self._thread.start()
        self.events.add("docker_watch", {"service": service})
        return {"ok": True, **self.status}

    def stop(self):
        """Ask the log follower to exit."""
        self._stop = True
        self.status = {"running": False, "service": self.status.get("service"), "error": None}
        return self.status

    def crashed(self, line):
        """True when a log line is a crash, not an ordinary error string."""
        return "Traceback (most recent call last)" in line or "exited with code" in line and "code 0" not in line

    def follow(self, service, intent):
        """Read the log until a crash, then run one Patch Loop. Further lines are ignored."""
        proc = subprocess.Popen(
            ["docker", "logs", "-f", "--tail", "50", service],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            for line in proc.stdout:
                if self._stop:
                    break
                if self.crashed(line):
                    self.events.add("docker_crash", {"service": service, "line": line.strip()[:200]})
                    self.patch_bonus.run(intent, k=5, max_attempts=1, dry_run=False, git_commit=False)
                    break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self.status = {"running": False, "service": service, "error": None}


docker_watch_service = DockerWatchService(bonus_event_repository, patch_bonus_service)
