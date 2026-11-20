ANSWER_MODEL = qwen2.5:3b
PATCH_MODEL = qwen2.5-coder:3b

.PHONY: build models up p1 test logs down clean

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

# Indexes the Target Project once. Run it while the server is stopped (one writer per Index).
p1:
	docker compose run --rm ioc python -m p1.index /workspace

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
