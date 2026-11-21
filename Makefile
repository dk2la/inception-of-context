# On 42 computers .school.env (written by `make school`) is loaded here: DOCKER_HOST, and COMPOSE when the
# machine has docker-compose or podman-compose instead of the `docker compose` plugin.
-include .school.env
COMPOSE ?= docker compose

ANSWER_MODEL = qwen2.5:3b
PATCH_MODEL = qwen2.5-coder:3b

.PHONY: build models up up-watch crash school purge p1 test lint logs down clean help \
	watch-check status files chunks file context ask ask-llm patch dry-run reindex events watch-demo target-test restore check

URL ?= http://localhost:8000
Q ?= what functions are in core.py?
INTENT ?= add a power function to Calculator
JSON = -H 'Content-Type: application/json'

# The tests also run inside the container:
#   docker compose run --rm -w /workspace ioc python -m pytest -q   (the Target Project)
#   docker compose run --rm ioc python -m pytest -q                 (this repository)

build:
	$(COMPOSE) build ioc

# Starts Ollama and downloads each model only if it is missing.
models:
	$(COMPOSE) up -d ollama
	until $(COMPOSE) exec -T ollama ollama list > /dev/null 2>&1; do sleep 1; done
	for model in $(ANSWER_MODEL) $(PATCH_MODEL); do \
		$(COMPOSE) exec -T ollama sh -c "ollama list | grep -q \"^$$model \" || ollama pull $$model" || exit 1; \
	done

up: build models
	$(COMPOSE) up -d ioc
	@echo "IoC is running at http://localhost:8000"

# Bonus: the same as up, plus the host's Docker socket, so Docker log watch can read other containers' logs.
WATCH = $(COMPOSE) -f docker-compose.yml -f docker-compose.watch.yml
# The host socket mounted into ioc: DOCKER_HOST if it is a unix socket, Podman's user socket on a machine where
# `docker` is Podman (42 computers), else Docker's default. Override with DOCKER_SOCK=/path/to/socket.
DOCKER_SOCK ?= $(shell scripts/docker_sock.sh)
export DOCKER_SOCK
up-watch: build models
	@if docker --version 2>/dev/null | grep -qi podman; then systemctl --user start podman.socket 2>/dev/null || true; fi
	@[ -S "$(DOCKER_SOCK)" ] || { echo "No Docker socket at $(DOCKER_SOCK). Podman: systemctl --user start podman.socket. Or: make up-watch DOCKER_SOCK=/path/to/socket"; exit 1; }
	$(WATCH) up -d ioc
	@echo "IoC is running at http://localhost:8000 (Docker log watch enabled, socket $(DOCKER_SOCK))"

# Docker log watch not working? Shows the socket on the host and what docker says from inside ioc.
watch-check:
	@echo "host socket: $(DOCKER_SOCK)"; ls -l "$(DOCKER_SOCK)" || true
	-$(WATCH) exec ioc ls -l /var/run/docker.sock
	-$(WATCH) exec ioc docker version

# Indexes the Target Project once. Run it while the server is stopped (one writer per Index).
p1:
	$(COMPOSE) run --rm ioc python -m p1.index /workspace

# flake8, using .flake8. The line limit is 120: the debug notes are longer than 79.
lint:
	python3 -m flake8 p1 p2 p3 bonus tests

# Every test of this repository (unit + end-to-end, with a fake model), with the coverage report,
# then the Target Project's own tests. Runs in the ioc image, on the code of this folder.
test: build
	$(COMPOSE) run --rm --no-deps -v "$(CURDIR)":/app -e TARGET_DIR=/app/target -e PYTHONDONTWRITEBYTECODE=1 \
		-e COVERAGE_FILE=/tmp/.coverage ioc sh -c "python -m coverage run -m pytest -q -p no:cacheprovider && python -m coverage report"
	$(COMPOSE) run --rm --no-deps -w /workspace -e PYTHONDONTWRITEBYTECODE=1 ioc python -m pytest -q -p no:cacheprovider

# ---------- 42 school computers ----------
school:        ## 42 computers: Docker's images and volumes into sgoinfre, background build (scripts/school_setup.sh)
	./scripts/school_setup.sh

purge:         ## 42 computers, after the defense: containers, volumes, images, sgoinfre data
	./scripts/school_setup.sh --uninstall

logs:
	$(COMPOSE) logs -f

down:
	$(COMPOSE) down

# Also deletes the Index and the downloaded models (several GB).
clean:
	$(COMPOSE) down -v

# ---------- Check the running system (after make up). Each target is one curl; override Q=... or INTENT=... ----------

help:          ## list the commands
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/'

status:        ## Part 1: chunk count, target, embedding and LLM models
	@curl -sS $(URL)/status; echo

files:         ## Part 1: every indexed file with its chunk count
	@curl -sS $(URL)/files; echo

chunks:        ## Part 1: the first 5 chunks of the Index
	@curl -sS "$(URL)/chunks?limit=5"; echo

file:          ## Part 1: calculator/core.py with its chunk boundaries
	@curl -sS "$(URL)/file?path=calculator/core.py"; echo

events:        ## Part 1: 5 seconds of the live Watcher feed (SSE)
	@curl -sS -N --max-time 5 $(URL)/events || true

watch-demo:    ## Part 1: create a file, ask about it, delete it, ask again
	@printf 'def negate(x):\n    return -x\n' > target/calculator/extra.py
	@sleep 3; curl -sS -X POST $(URL)/ask $(JSON) -d '{"question": "is there a function negate?"}'; echo
	@rm target/calculator/extra.py
	@sleep 3; curl -sS -X POST $(URL)/ask $(JSON) -d '{"question": "is there a function negate?"}'; echo

context:       ## Part 2: retrieval only, top 3 chunks for Q
	@curl -sS -X POST $(URL)/context $(JSON) -d '{"query": "$(Q)", "k": 3}'; echo

ask:           ## Part 2: answer Q (a symbol question skips the model)
	@curl -sS -X POST $(URL)/ask $(JSON) -d '{"question": "$(Q)"}'; echo

ask-llm:       ## Part 2: a question that needs the model
	@curl -sS -X POST $(URL)/ask $(JSON) -d '{"question": "what happens when you divide by zero?"}'; echo

patch:         ## Part 3: run the Patch Loop for INTENT (writes target/ when green; undo with make restore)
	@curl -sS -X POST $(URL)/patch $(JSON) -d '{"intent": "$(INTENT)"}'; echo

dry-run:       ## bonus: the diff INTENT would make, nothing written
	@curl -sS -X POST $(URL)/bonus/patch $(JSON) -d '{"intent": "$(INTENT)", "dry_run": true}'; echo

reindex:       ## bonus: full reindex now
	@curl -sS -X POST $(URL)/bonus/reindex; echo

crash:         ## bonus demo: run target/ as service "calculator"; its last job calls a missing method and crashes
	-@docker rm -f calculator > /dev/null 2>&1
	$(WATCH) run -d --name calculator calculator > /dev/null
	@echo 'Started container "calculator" (bonus/demo/calculator_job.py): 5 jobs, 1.5 s apart.'
	@echo 'Bonus tab, Docker log watch: container "calculator", Intent "add the missing power method to Calculator", Watch.'
	@echo 'After the Patch Loop: make crash again, and every job passes.'

target-test:   ## the Target Project's own tests, in the container
	$(COMPOSE) run --rm --no-deps -w /workspace -e PYTHONDONTWRITEBYTECODE=1 ioc python -m pytest -q -p no:cacheprovider

restore:       ## undo every patch in target/
	git checkout -- target/ && git clean -fdq target/

check: status files context ask ask-llm  ## quick tour of Parts 1 and 2 (no patch)
