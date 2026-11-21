ANSWER_MODEL = qwen2.5:3b
PATCH_MODEL = qwen2.5-coder:3b

.PHONY: build models up up-watch crash p1 test lint logs down clean help \
	status files chunks file context ask ask-llm patch dry-run reindex events watch-demo target-test restore check

URL ?= http://localhost:8000
Q ?= what functions are in core.py?
INTENT ?= add a power function to Calculator
JSON = -H 'Content-Type: application/json'

# The tests also run inside the container:
#   docker compose run --rm -w /workspace ioc python -m pytest -q   (the Target Project)
#   docker compose run --rm ioc python -m pytest -q                 (this repository)

build:
	docker compose build ioc

# Starts Ollama and downloads each model only if it is missing.
models:
	docker compose up -d ollama
	until docker compose exec -T ollama ollama list > /dev/null 2>&1; do sleep 1; done
	for model in $(ANSWER_MODEL) $(PATCH_MODEL); do \
		docker compose exec -T ollama sh -c "ollama list | grep -q \"^$$model \" || ollama pull $$model" || exit 1; \
	done

up: build models
	docker compose up -d ioc
	@echo "IoC is running at http://localhost:8000"

# Bonus: the same as up, plus the host's Docker socket, so Docker log watch can read other containers' logs.
WATCH = docker compose -f docker-compose.yml -f docker-compose.watch.yml
up-watch: build models
	$(WATCH) up -d ioc
	@echo "IoC is running at http://localhost:8000 (Docker log watch enabled)"

# Indexes the Target Project once. Run it while the server is stopped (one writer per Index).
p1:
	docker compose run --rm ioc python -m p1.index /workspace

# flake8, using .flake8. The line limit is 120: the debug notes are longer than 79.
lint:
	python3 -m flake8 p1 p2 p3 bonus tests

# Every test of this repository (unit + end-to-end, with a fake model), with the coverage report,
# then the Target Project's own tests. Runs in the ioc image, on the code of this folder.
test: build
	docker compose run --rm --no-deps -v "$(CURDIR)":/app -e TARGET_DIR=/app/target -e PYTHONDONTWRITEBYTECODE=1 \
		-e COVERAGE_FILE=/tmp/.coverage ioc sh -c "python -m coverage run -m pytest -q -p no:cacheprovider && python -m coverage report"
	docker compose run --rm --no-deps -w /workspace -e PYTHONDONTWRITEBYTECODE=1 ioc python -m pytest -q -p no:cacheprovider

logs:
	docker compose logs -f

down:
	docker compose down

# Also deletes the Index and the downloaded models (several GB).
clean:
	docker compose down -v

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

crash:         ## bonus: run the Target Project as container "calculator" and crash it (power overflow)
	-@docker rm -f calculator > /dev/null 2>&1
	-$(WATCH) run --name calculator calculator python -c \
		"from calculator.core import Calculator; print(Calculator().power(10, 400.0))"
	@echo 'Now Watch "calculator" in the Bonus tab, Intent: power must return inf instead of raising OverflowError'

target-test:   ## the Target Project's own tests, in the container
	docker compose run --rm --no-deps -w /workspace -e PYTHONDONTWRITEBYTECODE=1 ioc python -m pytest -q -p no:cacheprovider

restore:       ## undo every patch in target/
	git checkout -- target/ && git clean -fdq target/

check: status files context ask ask-llm  ## quick tour of Parts 1 and 2 (no patch)
