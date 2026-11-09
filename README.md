# Inception-of-Context

A local, offline coding assistant for a small codebase. It indexes the **Target Project** (a tiny
calculator in `target/`), answers questions about it without inventing functions, and applies changes that
are checked by the project's own tests, or rolls them back.

Everything runs in Docker. The only models are local [Ollama](https://ollama.com) models
(`qwen2.5:3b` and `qwen2.5-coder:3b`), and the embedding model is baked into the image at build time.
**No cloud LLM and no external API is ever contacted.**

The three parts of the subject are three folders, each one importing the previous one:

| Part | Folder | What it does |
|------|--------|--------------|
| 1 | `p1/` | **Index** + **Watcher**: cuts files into Chunks, stores them in ChromaDB, reindexes only what changed |
| 2 | `p2/` | API + RAG + dashboard: retrieval (vector + BM25), Questions answered from the Index |
| 3 | `p3/` | **Patch Loop**: Intent → Patch → Sanity Checks → apply → Validation Command → Rollback on failure |

## Requirements

- Docker Desktop (or Docker Engine with Compose) and `make`.
- A few GB of free disk space: the two models (about 2 GB each) are downloaded once by `make models`.

## Quick start: one command

```
make up
```

Then open <http://localhost:8000>.

`make up` builds the `ioc` image (including the embedding model), starts Ollama, pulls `qwen2.5:3b` and
`qwen2.5-coder:3b` if they are missing, and starts the `ioc` service (API, Watcher and dashboard).
The first run downloads the models; later runs take a few seconds.

## Step by step

```
make build    # build the ioc image (downloads the embedding model)
make models   # start ollama and pull both models (does nothing if they are present)
make p1       # index the Target Project once, from the console
make up       # start the API, the Watcher and the dashboard
```

- After `make models`: `docker compose exec ollama ollama list` shows both models.
- After `make p1`: it prints `indexed N chunks from M files`. Run it while `ioc` is **stopped**
  (`make down` first): only one process may write to the Index ([ADR-0002](docs/adr/0002-one-process-layered-parts.md)).
- After `make up`: the dashboard is at <http://localhost:8000>, and the Overview tab shows the same Chunk count.

## Other commands

| Command | What it does |
|---------|--------------|
| `make logs` | follow the logs of both containers |
| `make down` | stop everything; the Index and the models are kept |
| `make clean` | stop everything **and delete the Index and the downloaded models** (several GB, they will be downloaded again) |

## What you can try

1. **Watcher**: edit `target/calculator/core.py` and save. The Overview tab shows an `indexed` event, and in
   the ChromaDB Explorer only the Chunk you changed has a new id.
2. **Questions**, in the Ask & Retrieve tab: "is there a function power?" (no) and "what functions are in
   core.py?" (exactly `add`, `subtract`, `multiply`, `divide`). Both work in Russian too. These two are answered
   from the Index without calling the model ([ADR-0004](docs/adr/0004-symbol-questions-skip-the-llm.md)).
3. **Patch Loop**: in the Patch Loop tab, run the Intent "add a power function to Calculator". On CPU a full
   Patch Loop can take a minute or two. Restore the Target Project afterwards with `git checkout target/`.

The same from the command line:

```
curl -s localhost:8000/context -H 'content-type: application/json' \
     -d '{"query": "division by zero", "k": 3}'

curl -s localhost:8000/ask -H 'content-type: application/json' \
     -d '{"question": "is there a function power?", "k": 5}'

curl -s localhost:8000/patch -H 'content-type: application/json' \
     -d '{"intent": "add a power function to Calculator", "k": 5, "max_attempts": 3}'
```

## Running each part alone

```
python -m p1.index /workspace            # Part 1: index once and exit
python -m p1.index /workspace --watch    # Part 1: keep watching, print every reindex
uvicorn p2.app:app                       # Part 2 only: the Patch Loop tab says "not available"
uvicorn p3.app:app                       # Part 3 (what the container runs): Part 2 plus POST /patch
```

Inside Docker, prefix the Python commands with `docker compose run --rm ioc` (and stop the `ioc` service
first, so that only one process writes to the Index).

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `TARGET_DIR` | `/workspace` | the Target Project (in Docker: `./target`, mounted) |
| `CHROMA_DIR` | `/data/chroma` | where the Index lives (a Docker volume, outside the Target Project) |
| `OLLAMA_HOST` | `http://ollama:11434` | the local Ollama server |
| `WATCH_POLLING` | `0` | `1` makes the Watcher poll instead of relying on file notifications |

- **Faster models on a Mac.** Docker cannot use the GPU, so models run on the CPU. A native Ollama on the host is
  much faster and is still local: `OLLAMA_HOST=http://host.docker.internal:11434 make up`
  ([ADR-0003](docs/adr/0003-ollama-in-docker.md)).
- **Edits are not noticed?** Some bind mounts drop file notifications: `WATCH_POLLING=1 make up`.

## Tests

The tests never call a model (a fake replaces it) and never touch the real Index or the real `target/`.

```
python -m pytest -q                      # the repository tests, from the repository root
cd target && python -m pytest -q         # the Target Project's own tests
```

Inside Docker:

```
docker compose run --rm ioc python -m pytest -q                      # repository tests
docker compose run --rm -w /workspace ioc python -m pytest -q       # Target Project tests
```

## Project layout

```
target/        the Target Project: a calculator with its own tests and ioc.config.yml (the Validation Command)
p1/            Part 1: chunker.py, index.py (Index, Watcher, console command)
p2/            Part 2: search.py (retrieval), ask.py (Questions, the model call), app.py (API), static/index.html (dashboard)
p3/            Part 3: sanity.py (Sanity Checks), loop.py (Patch Loop), app.py (adds POST /patch)
tests/         tests of p1, p2 and p3
docs/          plan.md (the design), adr/ (the reasons behind it)
GLOSSARY.md    the words used everywhere: Chunk, Index, Watcher, Intent, Patch, Attempt, Rollback, ...
```

Read next: [`docs/plan.md`](docs/plan.md), [`GLOSSARY.md`](GLOSSARY.md), [`docs/adr/`](docs/adr/).
