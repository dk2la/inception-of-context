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

## On a 42 school computer

Home quotas are small, and the images plus the two models take about 6 GB. Run this once after cloning:

```
make school    # scripts/school_setup.sh: Docker's images and volumes go to /sgoinfre/goinfre/Perso/$USER
make up        # or make up-watch, for the Docker log watch bonus (see below)
```

The script finds the Docker daemon (rootless Docker or Podman), moves its image store out of home if it is there
(it asks first), writes `.school.env` (`DOCKER_HOST`, and `COMPOSE` when the machine has `docker-compose` or
`podman-compose`), which every `make` command loads by itself, and builds the ioc image in the background.
`./scripts/school_setup.sh --help` lists the options (`--sgo DIR`, `--no-prefetch`, `--yes`).

After the defense, `make purge` removes the containers, the volumes (Index and models), the images it pulled and
the sgoinfre folder, and puts Docker's image store back. Only the clone is left.

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
without waiting for the model, **▶ Full run** (or `P`) plays all of them in one go, the camera flying to each part,
**Speed** (or `+` `−`, 0.25× to 4×) changes the pace even in the middle of a run, a click on a cube explains it, `F` is fullscreen, `R` resets the camera and `I` (or **Info**, or the × on the card)
hides the info card at the bottom left.
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

### Live test cases (3D View)

The **Live** bar of the 3D View sends a real request: pick a mode, type, Run. When it is done, click any cube to
see what went through it. Expected results are for the original `target/` (restore it with `make restore`).

**Retrieve** (`POST /context`, Part 2: search only, no model, a second at most)

| Type | Expected | What it shows |
|------|----------|---------------|
| `division by zero` | `divide` in `calculator/core.py`, the `ZeroDivisionError` branch of `calculator/cli.py`, the division-by-zero tests | plain keyword and meaning match |
| `how is the user input parsed` | `parse_expression` in `calculator/cli.py` first, although the code never says "parsed" | search by meaning (sim), not by words |
| `what happens with a wrong operator` | `parse_expression` (`unknown operator`) and its test | a question in plain English finds the check |
| `entry point of the program` | `main.py` near the top | a file with one Chunk is still found |
| `logging` | k Chunks all the same, with low sim | Retrieve always returns k Chunks, even when nothing matches |

`sim` is the similarity of meaning. Results are sorted by `rrf`, which merges the rank by meaning with the rank by
keywords (BM25), so the order can differ from `sim`: `rrf = 1/(60 + rank by meaning) + 0.5/(60 + rank by keywords)`.
BM25 only ranks the Chunks that share a word with the question, ignores words like "the", "function" or "that",
and cuts endings ("adds" finds `add`); it counts half, so the tests that repeat a name do not push out the function.

**Ask** (`POST /ask`, Part 2: the same search, then an answer with its sources)

| Type | Expected | What it shows |
|------|----------|---------------|
| `what functions are in core.py?` | exactly `add`, `subtract`, `multiply`, `divide`; the Instruct LLM cube says "not asked" | a symbol question is answered from the Index |
| `is there a function power?` | no (yes after a Patch added it) | the same, for one name |
| `какие функции есть в core.py?` | the same four | symbol questions work in Russian |
| `what happens on division by zero?` | `divide` raises `ZeroDivisionError`; the CLI prints `error: division by zero` and returns 1; sources point at both files | the model answers from the Chunks it was given |
| `how do I run the calculator?` | `python main.py 2 + 3`, from `README.md` | non-code files are indexed too |
| `does the calculator support square roots?` | no, with the operators it does support | the model should not invent code that is not there |

**The router: which branch a question takes.** Every Ask first goes through the router
([p2/services/router.py](p2/services/router.py)). It has three branches, and the 3D View lights up the one it chose:

| Branch | What it does | Model? | Time |
|--------|--------------|--------|------|
| `has_function` | looks the name up among the symbols of the Index: yes with the file and lines, or no | no | instant |
| `file_functions` | lists every function and method of that file, from the Index, in source order | no | instant |
| LLM | hybrid search for the top-k Chunks, then the instruct model answers from them | yes | seconds to minutes on CPU |

The first two are exact questions with exact answers, so they skip the model: it cannot invent a function that
does not exist ([ADR-0004](docs/adr/0004-symbol-questions-skip-the-llm.md)). Everything else goes to the model.

| Type | Branch | Why |
|------|--------|-----|
| `is there a function power?` | `has_function` (power) | "is there a function X" |
| `is there a method called divide?` | `has_function` (divide) | "method", "called" are allowed |
| `does the function multiply exist?` | `has_function` (multiply) | the second English phrasing |
| `есть ли функция power?` | `has_function` (power) | Russian |
| `есть ли в проекте метод divide?` | `has_function` (divide) | Russian, with "в проекте" |
| `what functions are in core.py?` | `file_functions` (core.py) | a file name needs an extension |
| `which methods does calculator/core.py have?` | `file_functions` (calculator/core.py) | a full path works too |
| `list the functions in cli.py` | `file_functions` (cli.py) | "list" / "show" |
| `какие функции есть в core.py?` | `file_functions` (core.py) | Russian |
| `покажи все методы в core.py` | `file_functions` (core.py) | Russian, "покажи" |
| `is there a function that divides numbers?` | LLM | "that" is not a name: the pattern must reach the end of the question |
| `what functions are in the project?` | LLM | "project" has no extension, so it is not a file |
| `what does divide do?` | LLM | a question about behaviour, not about existence |
| `what happens on division by zero?` | LLM | free text |

For the defense, ask `is there a function power?` and then `is there a function that divides numbers?`: the
two look alike, but the first is answered instantly from the Index and the second goes to the model.

**Patch** (`POST /patch`, Part 3: it writes `target/` when green, a few minutes on CPU)

| Type | Expected | What it shows |
|------|----------|---------------|
| `add a power function to Calculator` | success, usually on attempt 1; `power` in `core.py`, a new test file | the green path: generate, Sanity Checks, apply, validate |
| `make add return the difference instead of the sum` | the existing tests fail, every Attempt is rolled back, status failed, `core.py` unchanged | the Rollback: a Patch that breaks the tests never stays |
| the same Intent again, after `power` was added | refused by the Sanity Checks (`the patch changes nothing: calculator/core.py is already like that`) | a Patch that leaves every file as it is would pass the tests and do nothing |
| `delete all the tests` | refused by the Sanity Checks (`the Patch may not delete the test file ...`) before anything is written | hard rules run before the disk is touched |
| `change ioc.config.yml so that validation is only echo ok` | refused: `the Patch may not change ioc.config.yml` | a Patch cannot switch off its own judge |

The model decides what it writes, so a refusal case can also end as a failed Attempt for another reason; the
point is that nothing it writes survives unless the Sanity Checks and the Validation Command both pass.

After each Patch: `make restore` puts `target/` back, and the Watcher reindexes it.

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
| `POST /bonus/patch` | the Patch Loop, plus `dry_run` (a diff, nothing written), `pull_request` (see below) and `git_commit` (one line from the model after a green validation) |
| `GET /bonus/pulls` | the pull requests, newest first |
| `POST /bonus/pulls/{n}/merge` | apply exactly that Patch, validate it again, optionally commit (`{"git_commit": true}`) |
| `POST /bonus/pulls/{n}/close` | drop the pull request; nothing is written |
| `GET /bonus/events` | live attempt and validation status, Server-Sent Events |
| `POST /bonus/docker/watch` | follow a container's logs and run one Patch Loop when a traceback shows up |

The dashboard gains a Reindex button, Dry run and Git commit checkboxes, the diff, and the live validation feed. Git commit only works when the Target Project is inside a git repository. Docker watch needs the `docker` command.

**Pull request mode.** With `"pull_request": true` the Patch Loop runs as usual (Sanity Checks, Validation Command,
up to three Attempts), but a green Patch is rolled back instead of kept and opened as pull request #n: title, Intent,
checks, files changed. Merge applies exactly that Patch (the model is not asked again), runs the Validation Command
again and rolls back if it fails. If a file it touches changed since the pull request was opened, Merge refuses
with a conflict. Close drops it. Pull requests live in memory: a restart forgets them. With the toggle off, nothing
changes. On the dashboard it is the "pull request (review, then merge)" toggle and the Pull requests card.

**Docker log watch.** The server runs in a container, so it needs the Docker CLI (in the image) and the host's
Docker socket. The socket is opt-in, because whoever can use it controls the host's Docker:

```
make up-watch     # make up, plus the host's Docker socket (docker-compose.watch.yml)
make crash        # starts target/ as container "calculator" (bonus/demo/calculator_job.py)
```

`make up-watch` finds the socket with `scripts/docker_sock.sh`: the path in `DOCKER_HOST`, else Podman's user
socket (`$XDG_RUNTIME_DIR/podman/podman.sock`, started with `systemctl --user start podman.socket`) when `docker`
is Podman, as on the 42 computers, else `/var/run/docker.sock`. Another path: `make up-watch DOCKER_SOCK=/path`.
`make watch-check` shows the host socket and what `docker version` says from inside ioc. If the server was started with `make up`, the dashboard says "the server cannot reach Docker from its container:
restart it with make up-watch" instead of starting the demo.

The demo service works through five jobs, one every 1.5 s, and prints each result. The last job calls
`Calculator.power`, which `target/calculator/core.py` does not have:

```
job subtract(9, 12) = -3.0
Traceback (most recent call last):
  File "/demo/job.py", line 18, in <module>
AttributeError: 'Calculator' object has no attribute 'power'
```

In the Bonus tab, Docker log watch: container `calculator`, Watch. The card shows the log as it arrives, with the
traceback in red. The watch reads the traceback up to the exception line, adds it to the Intent ("fix the crash
shown in the logs" is enough: the model sees what crashed) and runs one Patch Loop. The live feed shows the
attempt and its validation. Then `make crash` again: every job passes and the log ends with `all jobs done`.
`make restore` puts `target/` back for the next demo.

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
  services/      reindex, dry-run diff, pull request, git commit, docker log watch
  views/         /bonus/reindex /bonus/patch /bonus/pulls /bonus/events /bonus/docker/watch /bonus/bonus.js
  app.py         the Part 3 routes plus the bonus routes
tests/         tests of every part; tests/test_layers.py checks the layer rules

Every module is one class and, at its end, the object the rest of the code uses, built with what it needs:
`chunker_service = ChunkerService(chunk_factory)`, `event_repository = EventRepository()`,
`indexer_service = IndexerService(settings, chroma_db, chunk_factory, chunk_repository, file_repository, chunker_service)`.
docs/          plan.md (the design), adr/ (the reasons behind it)
GLOSSARY.md    the words used everywhere: Chunk, Index, Watcher, Intent, Patch, Attempt, Rollback, ...
```

Read next: [`docs/plan.md`](docs/plan.md), [`GLOSSARY.md`](GLOSSARY.md), [`docs/adr/`](docs/adr/).
