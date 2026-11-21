"""POST /bonus/docker/watch, POST /bonus/docker/stop and POST /bonus/docker/demo."""
from fastapi import APIRouter

from bonus.schemas.requests import DockerWatchRequest
from bonus.services.docker_demo import docker_demo_service
from bonus.services.docker_watch import docker_watch_service


class DockerWatchView:
    def __init__(self, docker_watch_service, docker_demo_service):
        # debug: POST /bonus/docker/watch, POST /bonus/docker/stop, and POST /bonus/docker/demo (the make crash button).
        self.docker_watch_service = docker_watch_service
        self.docker_demo_service = docker_demo_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/docker/watch", self.watch, methods=["POST"])
        self.router.add_api_route("/bonus/docker/stop", self.stop, methods=["POST"])
        self.router.add_api_route("/bonus/docker/demo", self.demo, methods=["POST"])
        self.router.add_api_route("/bonus/docker/demo/reset", self.reset, methods=["POST"])

    def watch(self, req: DockerWatchRequest):
        # debug: req.service == "calculator", req.intent == "fix the crash in Calculator.divide"
        # docker is present: return == {"ok": True, "running": True, "service": "calculator", "error": None}
        # no docker CLI: return["ok"] == False, error == "docker CLI is not available"
        return self.docker_watch_service.start(req.service, req.intent)

    def stop(self):
        # debug: POST /bonus/docker/stop. return == {"running": False, "service": "calculator", "error": None}
        return self.docker_watch_service.stop()

    def demo(self):
        # debug: POST /bonus/docker/demo -> {"ok": True, "service": "calculator", "error": None}
        return self.docker_demo_service.start()

    def reset(self):
        # debug: POST /bonus/docker/demo/reset -> {"ok": True, "restored": ["calculator/core.py"], "removed": [], ...}
        return self.docker_demo_service.reset()


docker_watch_view = DockerWatchView(docker_watch_service, docker_demo_service)
