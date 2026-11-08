# Inception-of-Context — entry points. `make help` lists them.
SHELL := /bin/bash
export IOC_UID := $(shell id -u)
export IOC_GID := $(shell id -g)
export IOC_PORT ?= 8000
export IOC_PART ?= p3
COMPOSE := docker compose
PY ?= .venv/bin/python

.PHONY: help up down restart logs ps build index models test clean reset-demo dev dev-index dev-test

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

up: build        ## build and start the stack (IOC_PART=p1|p2|p3), dashboard on http://localhost:$(IOC_PORT)
	$(COMPOSE) up -d
	@echo "Dashboard: http://localhost:$(IOC_PORT)  (part: $(IOC_PART))"
	@echo "First start pulls the two 3B models (~2 GB each) and the embedding model once: \`make logs\` to follow."

down:            ## stop the stack (keeps the index and downloaded models)
	$(COMPOSE) down

restart: down up ## restart everything

build:           ## build the image
	$(COMPOSE) build

logs:            ## follow logs
	$(COMPOSE) logs -f

ps:              ## show containers
	$(COMPOSE) ps

models:          ## pull / check the local LLMs only
	$(COMPOSE) up models

index:           ## one-shot index of the target inside the container
	$(COMPOSE) run --rm --no-deps ioc python p1/index.py /workspace

test: build      ## run the test suites inside the container
	$(COMPOSE) run --rm --no-deps -v $(CURDIR)/demo:/app/demo:ro ioc python -m pytest -q -p no:cacheprovider p1/tests p2/tests p3/tests

clean:           ## stop and delete volumes (index + cached models)
	$(COMPOSE) down -v --remove-orphans

reset-demo:      ## restore the demo target to its committed state
	git checkout -- demo && git clean -fdq demo

# --- without Docker -----------------------------------------------------------
.venv:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

dev: .venv       ## run locally without Docker (needs Python 3.11+ and a local `ollama serve`)
	$(PY) $(IOC_PART)/serve.py demo

dev-index: .venv ## index the demo locally once
	$(PY) p1/index.py demo

dev-test: .venv  ## run tests locally
	$(PY) -m pytest -q -p no:cacheprovider p1/tests p2/tests p3/tests
