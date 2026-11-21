#!/bin/sh
case "${DOCKER_HOST:-}" in
  unix://*) echo "${DOCKER_HOST#unix://}"; exit 0 ;;
esac
if docker --version 2>/dev/null | grep -qi podman; then
  echo "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
else
  echo /var/run/docker.sock
fi
