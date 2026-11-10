# Implementation plan

The agreed design for the Inception-of-Context subject (v1.1). Terms in **bold** are defined in [`GLOSSARY.md`](../GLOSSARY.md); the reasoning behind non-obvious choices lives in [`docs/adr/`](./adr/).

Guiding rule: the code is as short and plain as possible, so anyone who has written basic Python can follow it ([ADR-0001](./adr/0001-simplicity-first.md)).

## Stack

- Python 3.12 for everything.
- FastAPI for the HTTP server; the dashboard is a single `index.html` with vanilla JS, served as a static file (no build step).
- ChromaDB `PersistentClient` for the **Index**; embeddings from Chroma's built-in all-MiniLM-L6-v2 (ONNX, no PyTorch), downloaded once at image build time.
- Ollama with two models: `qwen2.5:3b` answers **Questions**, `qwen2.5-coder:3b` writes **Patches**.
- `watchdog` for the **Watcher**, `rank_bm25` for keyword ranking, `pyyaml`, `pytest`.
- Mandatory part only. No bonus until the mandatory part is solid.

## Repository layout

```
Makefile  README.md  Dockerfile  .dockerignore  docker-compose.yml  requirements.txt  .gitignore  GLOSSARY.md

target/                      Target Project (calculator), mounted as /workspace
  calculator/core.py         class Calculator: add, subtract, multiply, divide (floats)
  calculator/cli.py          parses "2 + 3"; division by zero → "error: division by zero", exit 1
  main.py                    python main.py 2 + 3  →  5
  tests/test_core.py         pytest
  tests/test_cli.py
  ioc.config.yml             validate: python -m py_compile {files} && python -m pytest -q
  README.md

p1/                          Part 1: Index + Watcher
  chunker.py                 file → list of Chunks
  index.py                   Chroma client, reindex_file(), index_all(), watch(), CLI

p2/                          Part 2: API + RAG (imports p1)
  search.py                  vector + BM25 over the whole Index, merged with RRF
  ask.py                     symbol-question router, otherwise KNOWN SYMBOLS + qwen2.5:3b
  app.py                     FastAPI routes + dashboard
  static/index.html          five tabs, vanilla JS

p3/                          Part 3: Patch Loop (imports the app from p2)
  sanity.py                  Sanity Checks, one small function each
  loop.py                    generate → sanity → apply → validate → rollback
  app.py                     p2 app + POST /patch
```

`.gitignore` covers the Chroma directory, model files, `__pycache__`, and `*.ioc.tmp`. The **Index** and the models only ever live in Docker volumes; nothing large is committed.

## Containers

| Service  | Runs | Volumes |
|----------|------|---------|
| `ioc`    | `python:3.12-slim`; uvicorn serving `p3.app` on port 8000, with the **Watcher** in a background thread of the same process, sharing one Chroma client ([ADR-0002](./adr/0002-one-process-layered-parts.md)) | `chroma_data:/data/chroma`, `./target:/workspace` |
| `ollama` | Ollama on CPU ([ADR-0003](./adr/0003-ollama-in-docker.md)); address overridable through `OLLAMA_HOST` | `ollama_models` |

The **Index** lives in `/data/chroma`, outside the **Target Project**, so the **Watcher** never reacts to its own writes.

## Part 1: Index and Watcher

**Chunking** (`p1/chunker.py`):
- Python: `ast`. One **Chunk** per function, async function, class, and method (decorators included), plus one module-header **Chunk** for imports and top-level code. Regex fallback if the file fails to parse.
- YAML: one **Chunk** per top-level key.
- Markdown: one **Chunk** per `#` heading.
- Anything else that is text: regex fallback on definition-like lines.
- Each **Chunk** stores: path, start/end line, symbol name, symbol kind, content hash.

**Incremental reindex** (`reindex_file(path)`, roughly ten lines):
- **Chunk** id = `sha256(path + "\n" + chunk text)`. Two **Chunks** with the same text in one file share one id and are stored once.
- Read the file's current ids from the **Index**, compute the new ids, delete the ones that disappeared, add the new ones, and leave matching ids alone. A **Chunk** whose text is unchanged but whose lines moved keeps its id; only its line numbers are updated.
- If the file no longer exists, delete all its **Chunks**.

**Skipped paths**: `node_modules`, `.git`, `dist`, `build`, `venv`, `.venv`, `__pycache__`, hidden directories, binary files, and `*.ioc.tmp`.

**Startup**: run `reindex_file` over every file (cheap, because unchanged **Chunks** keep their ids), then start the **Watcher**. This also catches edits made while the server was down.

**Watcher**: `watchdog` `Observer`; `WATCH_POLLING=1` switches to `PollingObserver` for bind mounts that drop inotify events. Every event calls `reindex_file` and appends `{time, type: indexed|deleted, path, chunks}` to an in-memory event list.

**CLI**: `python -m p1.index /workspace` indexes once; `--watch` keeps watching.

## Part 2: API and RAG

| Route | Returns |
|-------|---------|
| `GET /status` | **Chunk** count, target path, Chroma path, both model names, Ollama URL |
| `GET /files` | files with their **Chunk** counts |
| `GET /file?path=` | file content plus **Chunk** boundaries |
| `GET /chunks?offset=&limit=` | paginated **Chunks** (`limit` at most 200) |
| `POST /context {query, k}` | top-k **Chunks** with vector similarity and final score |
| `POST /ask {question, k}` | answer plus the **Chunks** used as sources |
| `GET /events` | Server-Sent Events: every half second, sends events added to the list since the last send |

A route that needs the model answers `503` with the reason when Ollama cannot be reached.

**Retrieval** (`p2/search.py`): rank the whole **Index** twice (vector similarity from Chroma and BM25 over the Chroma documents), then merge with Reciprocal Rank Fusion: `score = 1/(60 + vector_rank) + 1/(60 + bm25_rank)`. Chroma stays the canonical store; the BM25 index is rebuilt from it whenever the **Index** changes.

**Answering** (`p2/ask.py`), single-turn, no conversation history:
1. Regex router (English and Russian phrasing): "is there a function X?" and "what functions are in file Y?" are answered straight from **Index** metadata, without calling the LLM ([ADR-0004](./adr/0004-symbol-questions-skip-the-llm.md)).
2. Every other **Question** goes to `qwen2.5:3b` with the retrieved **Chunks** and a `KNOWN SYMBOLS` block listing the real symbols of the retrieved files. The model may not name symbols outside that list.

## Part 3: Patch Loop

`POST /patch {intent, k, max_attempts}` is synchronous and returns `{status, attempts: [...], patch}`. Each **Attempt** records generation, **Sanity Check**, apply, and validation results. `max_attempts` is clamped to 1..3. One **Patch Loop** runs at a time; a second request waits for the first to finish.

**Generation**: `qwen2.5-coder:3b` is called with `"format": "json"` and receives:
1. the list of all files in the **Target Project**,
2. the **full** content of every file hit by the top-k **Chunks**, each preceded by a `=== FILE: path ===` marker,
3. the **Intent** and the required shape `{summary, files: [{path, op: create|modify|delete, content}]}`.

On later **Attempts** it also receives its previous **Patch** and the failure reason (the last ~40 lines of the validation log, or the **Sanity Check** refusal).

**Sanity Checks** (`p3/sanity.py`), hard refusals before any disk write. Each check is a small function returning a reason or `None`. Reject a **Patch** that:
1. contains a `=== FILE:` retrieval marker,
2. creates a file that already exists,
3. replaces a non-empty file with `""`, `"None"`, or `"null"`,
4. defines a function whose body (docstring aside) is only `pass`, `...`, `return None`, or nothing at all (found with `ast`),
5. shrinks an existing file by more than 60 %,
6. touches more than three files,
7. has a path outside the **Target Project** (absolute paths, `..`),
8. touches `ioc.config.yml` in any letter case (bind mounts can be case-insensitive), so the model cannot weaken the **Validation Command**,
9. has a path that is a folder.

**Apply**: take a **Snapshot** of every file the **Patch** touches (recording files that do not exist yet), write each new content to `<file>.ioc.tmp`, then `os.replace` each one once all temporaries are ready.

**Validate**: run the **Validation Command** from `ioc.config.yml`, with `{files}` replaced by the changed `.py` files (or `-`, so `py_compile` compiles nothing, when none changed), in `/workspace`, with a 60-second timeout. A timeout kills the whole process group and is a failed **Attempt**. The command runs with `PYTHONPYCACHEPREFIX` set to a temporary folder and `PYTEST_ADDOPTS=-p no:cacheprovider`, so it leaves no `.pyc` or `.pytest_cache` in the **Target Project** and a **Rollback** can never run stale bytecode.

**Failure**: a failed **Attempt** (including a **Sanity Check** refusal) is rolled back to its **Snapshot** immediately, so every **Attempt** starts from the original code ([ADR-0005](./adr/0005-rollback-after-every-attempt.md)). After three failed **Attempts**, the **Target Project** is byte-for-byte what it was before the **Intent**: every file, and no folder made for a file that was created.

**Success**: the **Watcher** picks up the changed files and reindexes them; no extra code is needed.

## Dashboard

One `p2/static/index.html` with five tabs:
- **Overview**: status cards, per-file **Chunk** counts, live activity feed from `/events`.
- **Files**: file content with **Chunk** boundaries marked.
- **ChromaDB Explorer**: paginated table from `/chunks`.
- **Ask & Retrieve**: text box, `k` selector, Retrieve and Ask buttons, answer and ranked sources.
- **Patch Loop**: **Intent**, `k`, max attempts, run button, the result of every **Attempt**, final **Patch** as JSON. Shows "not available" until `/patch` exists (p3).

## Makefile

```
make build    build the ioc image (downloads the embedding model)
make models   start ollama and pull qwen2.5:3b + qwen2.5-coder:3b (no-op if present)
make up       build + models + start ioc  →  http://localhost:8000
make p1       index the Target Project once, from the console
make logs     follow logs
make down     stop everything
make clean    down -v: also deletes the Index and the models
```

The README documents both paths: one command (`make up`) and step by step (`make build` → `make models` → `make p1` → `make up`).

## Build order

Each step ends with a check that proves it works.

1. **Skeleton**: calculator + tests, `ioc.config.yml`, Dockerfile, compose, Makefile, `.gitignore`.
   *Check*: `make models` succeeds; `pytest` passes inside the `ioc` container.
2. **p1**: chunker, index, Watcher, plus the Overview, Files, and Explorer tabs.
   *Check*: editing `core.py` changes only its **Chunks**; deleting a file removes its **Chunks**.
3. **p2**: retrieval, `/ask`, and the Ask & Retrieve tab.
   *Check*: "is there a function `power`?" → no. "What functions are in core.py?" → exactly the four methods.
4. **p3**: **Sanity Checks**, the **Patch Loop**, and the Patch Loop tab.
   *Check*: "add `power`" succeeds. An **Intent** built to fail ends in three failed **Attempts** and a **Rollback**, after which `git diff target/` is empty.
5. **README**, then a clean run: `make clean && make up`.
