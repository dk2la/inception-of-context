"""POST /bonus/docker/watch and POST /bonus/docker/stop."""
from fastapi import APIRouter

from bonus.schemas.requests import DockerWatchRequest
from bonus.services.docker_watch import docker_watch_service


class DockerWatchView:
    def __init__(self, docker_watch_service):
        self.docker_watch_service = docker_watch_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/docker/watch", self.watch, methods=["POST"])
        self.router.add_api_route("/bonus/docker/stop", self.stop, methods=["POST"])

    def watch(self, req: DockerWatchRequest):
        return self.docker_watch_service.start(req.service, req.intent)

    def stop(self):
        return self.docker_watch_service.stop()


docker_watch_view = DockerWatchView(docker_watch_service)
