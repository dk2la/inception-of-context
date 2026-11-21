# Inception-of-Context

A local, offline coding assistant for a small codebase. It indexes the **Target Project** (a tiny
calculator in `target/`), answers questions about it without inventing functions, and applies changes that
are checked by the project's own tests, or rolls them back.

Everything runs in Docker. The only models are local [Ollama](https://ollama.com) models
(`qwen2.5:3b` and `qwen2.5-coder:3b`), and the embedding model is baked into the image at build time.
**No cloud LLM and no external API is ever contacted.**

The three parts of the subject are three folders, each one using the previous one. Inside each part the code is
split into the same layers (see [Project layout](#project-layout)):

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

### The dashboard

Six tabs, keys `1`–`6`: Overview (System map, status, live Watcher events), Files, ChromaDB Explorer, Ask & Retrieve,
Patch Loop, and **3D View**. The 3D View shows the three parts as stacked levels, one cube per step; the cubes follow
the live system. For a demo: **Tour** (or `←` `→`) walks through every step with an explanation and the file that does
it, the **Replay** buttons play each flow (indexing, a symbol question, an LLM question, a green patch, a rollback)
without waiting for the model, a click on a cube explains it, `F` is fullscreen and `R` resets the camera.
It is plain CSS 3D: nothing is downloaded, it works offline.

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
uvicorn p3.app:app                       # Part 3 only: Part 2 plus POST /patch
uvicorn bonus.app:app                    # what the container runs: Part 3 plus the bonus routes
```

Inside Docker, prefix the Python commands with `docker compose run --rm ioc` (and stop the `ioc` service
first, so that only one process writes to the Index).

## Bonus

`bonus/` is optional and is what `make up` serves. The mandatory routes are unchanged. The extra ones:

| Route | What it does |
|-------|----------------|
| `POST /bonus/reindex` | full reindex on demand |
| `POST /bonus/patch` | the Patch Loop, plus `dry_run` (a diff, nothing written) and `git_commit` (one line from the model after a green validation) |
| `GET /bonus/events` | live attempt and validation status, Server-Sent Events |
| `POST /bonus/docker/watch` | follow a container's logs and run one Patch Loop when a traceback shows up |

The dashboard gains a Reindex button, Dry run and Git commit checkboxes, the diff, and the live validation feed. Git commit only works when the Target Project is inside a git repository. Docker watch needs the `docker` command.

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
make test                                # everything in Docker: repository tests with coverage, then the Target Project's tests
make lint                                # flake8 on p1, p2, p3, bonus and tests (.flake8, 120 columns)
python -m pytest -q                      # the repository tests, from the repository root
python -m pytest -q tests/e2e            # only the end-to-end tests
cd target && python -m pytest -q         # the Target Project's own tests
```

- `tests/test_*.py`: every layer of every part, and `bonus/`, at 100% line and branch coverage (`.coveragerc`).
- `tests/test_layers.py`: the layer rules: views → services → repositories → models, a part imports only earlier
  parts, only `p1/core` talks to Chroma and to Ollama. Source lives in `p1/`, `p2/`, `p3/`, and the optional `bonus/`.
- `tests/e2e/`: the real server started with uvicorn over a copy of `target/`, with a fake Ollama that answers from a
  script. They check each requirement of the subject from the outside: indexing, the Watcher, questions, the Patch
  Loop with byte-exact rollback, the sanity refusals and the 503 when Ollama is down.

Inside Docker:

```
docker compose run --rm ioc python -m pytest -q                      # repository tests
docker compose run --rm -w /workspace ioc python -m pytest -q       # Target Project tests
```

## Project layout

```
target/        the Target Project: a calculator with its own tests and ioc.config.yml (the Validation Command)
p1/            Part 1, Index + Watcher, and what every part shares
  config/        settings.py: every setting (environment variables and limits)
  core/          chroma_db.py (ChromaDB, the one Chroma client), llm.py (LLMClient, the only call to the model)
  models/        Chunk, Event
  schemas/       response bodies of the Part 1 routes
  repositories/  chunk_repository (writes and browses the Index), file_repository (disk), event_repository
  services/      chunker, indexer, watcher, overview
  views/         /status /files /file /chunks, /events
  index.py       the console command
p2/            Part 2, retrieval + answers + dashboard
  models/        Answer
  schemas/       bodies of /context and /ask
  repositories/  search_repository (reads the Index for retrieval)
  services/      search (vector + BM25 + RRF), router (symbol questions), ask
  views/         /context /ask, / (dashboard, static/index.html), errors (503)
  app.py         the FastAPI app (Part 1 + Part 2 routes, the Watcher in the background)
p3/            Part 3, Patch Loop
  models/        Patch, Attempt
  schemas/       bodies of /patch
  repositories/  target_files (Snapshot, apply, Rollback)
  services/      sanity, validation, patch_loop
  views/         /patch
  app.py         the Part 2 app plus /patch
bonus/         optional Chapter VII bonuses; this is the app `make up` serves
  services/      reindex, dry-run diff, git commit, docker log watch
  views/         /bonus/reindex /bonus/patch /bonus/events /bonus/docker/watch /bonus/bonus.js
  app.py         the Part 3 routes plus the bonus routes
tests/         tests of every part; tests/test_layers.py checks the layer rules

Every module is one class and, at its end, the object the rest of the code uses, built with what it needs:
`chunker_service = ChunkerService(chunk_factory)`, `event_repository = EventRepository()`,
`indexer_service = IndexerService(settings, chroma_db, chunk_factory, chunk_repository, file_repository, chunker_service)`.
docs/          plan.md (the design), adr/ (the reasons behind it)
GLOSSARY.md    the words used everywhere: Chunk, Index, Watcher, Intent, Patch, Attempt, Rollback, ...
```

Read next: [`docs/plan.md`](docs/plan.md), [`GLOSSARY.md`](GLOSSARY.md), [`docs/adr/`](docs/adr/).
