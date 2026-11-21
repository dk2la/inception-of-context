"""Watch one container's logs and run a single Patch Loop when it crashes."""
import shutil
import subprocess
import threading

from p1.config.settings import settings
from bonus.repositories.event_repository import bonus_event_repository
from bonus.services.docker_demo import daemon_unreachable, unreachable_reason
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
        problem = self.daemon_problem()
        if problem:
            self.status = {"running": False, "service": service, "error": problem}
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

    def daemon_problem(self):
        """Why docker cannot be used from here, or None. Asked before following, so the card says it at once."""
        try:
            done = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                  capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as error:
            return f"docker is not usable here: {error}"
        if done.returncode == 0:
            return None
        if daemon_unreachable(done.stderr + done.stdout):
            return unreachable_reason(done.stderr + done.stdout)
        return done.stderr.strip()[-300:] or "docker failed"

    def stop(self):
        """Ask the log follower to exit."""
        self._stop = True
        self.status = {"running": False, "service": self.status.get("service"), "error": None}
        return self.status

    def crashed(self, line):
        """True when a log line is a crash, not an ordinary error string."""
        return "Traceback (most recent call last)" in line or "exited with code" in line and "code 0" not in line

    def follow(self, service, intent):
        """Read the log until a crash, then run one Patch Loop. Every line goes to the live feed."""
        proc = subprocess.Popen(
            ["docker", "logs", "-f", "--tail", "50", service],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        traceback = []
        try:
            for line in proc.stdout:
                if self._stop:
                    break
                self.events.add("docker_log", {"service": service, "line": line.rstrip("\n")[:400]})
                if traceback:
                    traceback.append(line.rstrip("\n"))
                    if line[:1] not in (" ", "\t"):
                        self.patch_after_crash(service, intent, traceback)
                        break
                elif "Traceback (most recent call last)" in line:
                    traceback = [line.rstrip("\n")]
                elif self.crashed(line):
                    self.patch_after_crash(service, intent, [line.rstrip("\n")])
                    break
            else:
                if traceback:
                    self.patch_after_crash(service, intent, traceback)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self.status = {"running": False, "service": service, "error": None}

    def patch_after_crash(self, service, intent, lines):
        """Tell the feed what crashed, then run one Patch Loop whose Intent includes the crash."""
        crash = "\n".join(lines[-40:])
        self.events.add("docker_crash", {"service": service, "line": lines[-1].strip()[:200], "traceback": crash})
        full_intent = f"{intent}\n\nThe container {service} crashed. The end of its log:\n{crash}"
        result = self.patch_bonus.run(full_intent, k=5, max_attempts=settings.MAX_ATTEMPTS, dry_run=False,
                                      git_commit=False)
        if result and result.get("status") == "success":
            self.verify(service)

    def verify(self, service):
        """After a green Patch, run the container again and show its new log: proof that the crash is gone."""
        self.events.add("docker_rerun", {"service": service})
        proc = subprocess.Popen(["docker", "start", "-a", service],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        crashed = False
        try:
            for line in proc.stdout:
                self.events.add("docker_log", {"service": service, "line": line.rstrip("\n")[:400]})
                crashed = crashed or "Traceback (most recent call last)" in line
            code = proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = None
        ok = not crashed and code == 0
        self.events.add("docker_verified", {"service": service, "ok": ok, "exit_code": code})


docker_watch_service = DockerWatchService(bonus_event_repository, patch_bonus_service)
