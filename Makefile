ANSWER_MODEL = qwen2.5:3b
PATCH_MODEL = qwen2.5-coder:3b

.PHONY: build models up logs down clean

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

logs:
	docker compose logs -f

down:
	docker compose down

# Also deletes the Index and the downloaded models (several GB).
clean:
	docker compose down -v
