#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SGO_BASE="/sgoinfre/goinfre/Perso/$USER"; SGO=""; PREFETCH=1; YES=0; UNINSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sgo) SGO="$2"; shift 2 ;;
    --no-prefetch) PREFETCH=0; shift ;;
    --yes|-y) YES=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown option $1 (see --help)"; exit 2 ;;
  esac
done
SGO="${SGO:-$SGO_BASE/inception-of-context}"
STATE="$SGO/state"; LOGS="$SGO/logs"
G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'
say()  { echo "${B}==>${N} $*"; }
ok()   { echo "  ${G}ok${N}  $*"; }
warn() { echo "  ${Y}!!${N}  $*"; }
die()  { echo "  ${R}xx${N}  $*"; exit 1; }
ask()  { [[ $YES == 1 ]] && return 0; read -r -p "  $1 [Y/n] " a; [[ -z "$a" || "$a" =~ ^[Yy] ]]; }
mark() { mkdir -p "$STATE"; echo "$1" >> "$STATE/done"; }
did()  { [[ -f "$STATE/done" ]] && grep -qx "$1" "$STATE/done"; }
T0=$SECONDS

find_compose() {
  if docker compose version >/dev/null 2>&1; then echo "docker compose"
  elif command -v docker-compose >/dev/null; then echo "docker-compose"
  elif command -v podman-compose >/dev/null; then echo "podman-compose"
  fi
}

find_docker_host() {
  if docker --version 2>/dev/null | grep -qi podman; then
    systemctl --user start podman.socket 2>/dev/null
    echo "unix://${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
  else
    docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null
  fi
}

if [[ $UNINSTALL == 1 ]]; then
  did setup || die "$SGO was not created by this script (no $STATE/done): nothing removed — check --sgo"
  say "Removing what school_setup.sh and make up created"
  [[ -f .school.env ]] && set -a && . ./.school.env && set +a
  COMPOSE="${COMPOSE:-$(find_compose)}"
  if [[ -n "$COMPOSE" ]]; then
    $COMPOSE -f docker-compose.yml -f docker-compose.watch.yml --profile demo down -v --rmi local --remove-orphans \
      >/dev/null 2>&1 && ok "containers, volumes (Index, models) and the ioc image"
  fi
  if [[ -f "$STATE/images" ]] && command -v docker >/dev/null; then
    while read -r img; do docker rmi "$img" >/dev/null 2>&1 && ok "image $img"; done < "$STATE/images"
  fi
  if did docker-moved; then
    if [[ -f "$STATE/daemon.json.bak" ]]; then cp "$STATE/daemon.json.bak" "$HOME/.config/docker/daemon.json"
    else rm -f "$HOME/.config/docker/daemon.json"; fi
    systemctl --user restart docker 2>/dev/null; ok "Docker image store back to its default place"
  fi
  if did podman-moved; then
    if [[ -f "$STATE/storage.conf.bak" ]]; then cp "$STATE/storage.conf.bak" "$HOME/.config/containers/storage.conf"
    else rm -f "$HOME/.config/containers/storage.conf"; fi
    ok "Podman storage back to its default place"
  fi
  if did podman-registries; then
    if [[ -f "$STATE/registries.conf.bak" ]]; then cp "$STATE/registries.conf.bak" "$HOME/.config/containers/registries.conf"
    else rm -f "$HOME/.config/containers/registries.conf"; fi
    ok "Podman registries config restored"
  fi
  rm -f .school.env && ok ".school.env"
  chmod -R u+w "$SGO" 2>/dev/null; rm -rf "$SGO" && ok "$SGO"
  echo; echo "Left: the clone itself. Remove it with:  rm -rf \"$ROOT\""
  exit 0
fi

say "1. Folders"
[[ "$(uname -s)" == Linux ]] || warn "not Linux: fine for a dry run, the script targets the school computers"
if [[ ! -d "$(dirname "$SGO")" ]]; then
  mkdir -p "$(dirname "$SGO")" 2>/dev/null || die "cannot create $(dirname "$SGO") — is /sgoinfre mounted? use --sgo DIR"
  chmod 700 "$(dirname "$SGO")"
fi
mkdir -p "$SGO" "$LOGS" "$STATE" && chmod 700 "$SGO" || die "cannot write $SGO"
did setup || mark setup
ok "data in $SGO ($(df -h "$SGO" | awk 'NR==2{print $4}') free), home has $(df -h "$HOME" | awk 'NR==2{print $4}') free"

say "2. Tools"
for tool in make git curl; do
  command -v "$tool" >/dev/null && ok "$tool" || warn "$tool not found"
done
command -v docker >/dev/null || die "no docker command: this project runs entirely in Docker (or podman-docker)"
DH=$(find_docker_host); [[ -n "$DH" ]] && export DOCKER_HOST="$DH"
COMPOSE=$(find_compose)
[[ -n "$COMPOSE" ]] || die "no compose: need 'docker compose', docker-compose or podman-compose"
ok "docker $(docker --version | awk '{print $3}' | tr -d ,) · compose: $COMPOSE${DH:+ · DOCKER_HOST=$DH}"

say "3. Docker"
PODMAN=0; docker --version 2>/dev/null | grep -qi podman && PODMAN=1
if [[ $PODMAN == 1 ]]; then
  reg="$HOME/.config/containers/registries.conf"
  if ! grep -qs 'unqualified-search-registries *= *\["docker.io"\]' "$reg"; then
    mkdir -p "$HOME/.config/containers"
    [[ -f "$reg" ]] && cp "$reg" "$STATE/registries.conf.bak"
    printf 'unqualified-search-registries = ["docker.io"]\nshort-name-mode = "permissive"\n' > "$reg"
    mark podman-registries
  fi
  ok "Podman: short image names resolve on docker.io"
fi
if root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null) || root=$(docker info --format '{{.Store.GraphRoot}}' 2>/dev/null); then
  ok "daemon reachable, images and volumes stored in $root"
  case "$root/" in
    "$HOME"/*)
      warn "images and the models (~6 GB together) would fill your home quota"
      if ask "move the image store to $SGO/docker?"; then
        if [[ $PODMAN == 1 ]]; then
          mkdir -p "$HOME/.config/containers" "$SGO/containers"
          [[ -f "$HOME/.config/containers/storage.conf" ]] && cp "$HOME/.config/containers/storage.conf" "$STATE/storage.conf.bak"
          printf '[storage]\ndriver = "overlay"\ngraphroot = "%s"\n' "$SGO/containers" > "$HOME/.config/containers/storage.conf"
          podman system migrate >/dev/null 2>&1; systemctl --user restart podman.socket 2>/dev/null; mark podman-moved
        else
          mkdir -p "$HOME/.config/docker" "$SGO/docker"
          f="$HOME/.config/docker/daemon.json"; [[ -f "$f" ]] && cp "$f" "$STATE/daemon.json.bak"
          python3 - "$f" "$SGO/docker" <<'PY'
import json, os, sys
f, root = sys.argv[1], sys.argv[2]
d = json.load(open(f)) if os.path.exists(f) and os.path.getsize(f) else {}
d["data-root"] = root
json.dump(d, open(f, "w"), indent=2)
PY
          systemctl --user restart docker || die "could not restart rootless Docker (systemctl --user restart docker)"
          mark docker-moved
        fi
        root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || docker info --format '{{.Store.GraphRoot}}' 2>/dev/null)
        ok "images and volumes now stored in $root"
      else
        warn "kept in home: watch your quota (df -h ~)"
      fi ;;
  esac
else
  die "docker daemon not reachable (not started, or you are not in the docker group)"
fi

SOCK="${DH#unix://}"
{
  echo "# written by scripts/school_setup.sh. make loads it by itself; in a shell: set -a; . ./.school.env; set +a"
  [[ -n "$DH" ]] && echo "export DOCKER_HOST=$DH"
  [[ "$(uname -s)" == Linux && "$DH" == unix://* ]] && echo "export DOCKER_SOCK=$SOCK"
  [[ "$COMPOSE" != "docker compose" ]] && echo "export COMPOSE=$COMPOSE"
} > .school.env
ok "wrote .school.env"

if [[ $PREFETCH == 1 ]]; then
  for img in docker.io/ollama/ollama:latest docker.io/library/python:3.12-slim docker.io/library/docker:27.3.1-cli; do
    docker image inspect "$img" >/dev/null 2>&1 || echo "$img" >> "$STATE/images"
  done
  [[ -f "$STATE/images" ]] && sort -u -o "$STATE/images" "$STATE/images"
  ( echo "pull ollama/ollama"; docker pull docker.io/ollama/ollama:latest >/dev/null 2>&1 && echo "done ollama" || echo "FAILED ollama"
    echo "build ioc"; $COMPOSE build ioc > "$LOGS/build.log" 2>&1 && echo "done ioc" || echo "FAILED ioc (see $LOGS/build.log)"
    echo "ALL DONE" ) > "$LOGS/prefetch.log" 2>&1 &
  echo $! > "$STATE/prefetch.pid"
  ok "building ioc and pulling ollama in the background — progress: tail -f $LOGS/prefetch.log"
fi

echo
say "Ready in $((SECONDS - T0)) s.  Home: $(du -sh "$ROOT" 2>/dev/null | cut -f1) clone;  sgoinfre: $SGO"
cat <<EOF

  ${B}make up${N}        # http://localhost:8000 — downloads the two models on the first run (~4 GB, into sgoinfre)
  make check     # quick tour of Parts 1 and 2
  make test      # every test, in the container
$( [[ $PREFETCH == 1 ]] && echo "  tail -f $LOGS/prefetch.log    # the background build" )
  make purge     # when you leave: containers, volumes, images, sgoinfre data
EOF
