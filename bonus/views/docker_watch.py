"""POST /bonus/docker/watch, POST /bonus/docker/stop and POST /bonus/docker/demo."""
from fastapi import APIRouter

from bonus.schemas.requests import DockerWatchRequest
from bonus.services.docker_demo import docker_demo_service
from bonus.services.docker_watch import docker_watch_service


class DockerWatchView:
    def __init__(self, docker_watch_service, docker_demo_service):
        self.docker_watch_service = docker_watch_service
        self.docker_demo_service = docker_demo_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/docker/watch", self.watch, methods=["POST"])
        self.router.add_api_route("/bonus/docker/stop", self.stop, methods=["POST"])
        self.router.add_api_route("/bonus/docker/demo", self.demo, methods=["POST"])
        self.router.add_api_route("/bonus/docker/demo/reset", self.reset, methods=["POST"])

    def watch(self, req: DockerWatchRequest):
        return self.docker_watch_service.start(req.service, req.intent)

    def stop(self):
        return self.docker_watch_service.stop()

    def demo(self):
        return self.docker_demo_service.start()

    def reset(self):
        return self.docker_demo_service.reset()


docker_watch_view = DockerWatchView(docker_watch_service, docker_demo_service)
