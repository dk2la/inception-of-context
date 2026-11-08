# Ollama runs in Docker Compose, on CPU

Ollama runs as a `docker compose` service with models in a named volume, so the whole stack comes up with `make up` on any machine and stays inside the isolated environment the subject requires. On macOS this means no GPU (Docker cannot reach Metal), so a 3B model generates only around 5–10 tokens/s and a full Patch Loop can take a minute or two. This is accepted. For faster local development, `OLLAMA_HOST` can point the `ioc` service at a native Ollama on the host without any code change.

## Considered Options

- Native Ollama on the host, reached via `host.docker.internal`: fast on Apple Silicon, but the evaluator's machine must have Ollama installed, and the project is no longer self-contained.
