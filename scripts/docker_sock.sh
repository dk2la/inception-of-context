#!/bin/sh
# Prints the host socket of the container engine, for docker-compose.watch.yml (make up-watch).
#   DOCKER_HOST=unix:///path  -> /path
#   docker is Podman (42)     -> $XDG_RUNTIME_DIR/podman/podman.sock
#   otherwise                 -> /var/run/docker.sock
case "${DOCKER_HOST:-}" in
  unix://*) echo "${DOCKER_HOST#unix://}"; exit 0 ;;
esac
if docker --version 2>/dev/null | grep -qi podman; then
  echo "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
else
  echo /var/run/docker.sock
fi
