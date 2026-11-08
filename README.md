# Inception-of-Context (IoC)

A local, self-hosted coding assistant: it indexes a codebase into a vector
store, answers questions about it with a small local model, and turns a
textual intent into a validated patch that rolls back on failure.
**Everything runs locally**: no remote LLM is ever called.

| Part | Folder | What it does |
|---|---|---|
| 1 | [`p1/`](p1) | Logical chunking (AST), local embeddings (all-MiniLM-L6-v2), persistent ChromaDB, incremental watcher, dashboard *Overview* + *Files* |
| — | [`demo/`](demo) | The target project: a tiny notes app with its own `ioc.config.yml` |

## Quick start

Requirements: Docker with Compose v2, `make`, about 1 GB of free disk for part 1.

```bash
make up          # build + start, then open http://localhost:8000
make logs        # follow what the indexer / watcher does
make down        # stop (index and cached model are kept in a volume)
make clean       # stop and delete the index + cached model
```

The first start downloads the embedding model (`all-MiniLM-L6-v2`, ONNX, ~80 MB)
into the `ioc-data` volume. Every later start loads it from disk and works offline.

Try the watcher: with the dashboard open on *Overview*, edit, create or delete a
file under `demo/`. The *Live activity* feed shows exactly which chunks
were added, re-embedded or removed. `make reset-demo` restores the demo.

Other `make` targets: `make help`. Point the system at another small project with
`IOC_TARGET_DIR=/path/to/project make up`.

### Without Docker

```bash
make dev         # creates .venv, installs requirements, serves the dashboard on :8000
make dev-index   # index ./demo once and print stats
make dev-test    # run the test suites
```

## Part 1: indexing and synchronization

```
python p1/index.py <target>             # index once, print stats
python p1/index.py <target> --watch     # index, then keep the collection in sync
python p1/index.py <target> --serve     # index + watch + dashboard/API
```

* **Logical chunking** ([`chunker.py`](p1/ioc_index/chunker.py)). Python is parsed with `ast`: one chunk
  per function, per method (nested in classes, decorators included), per class header
  and per module-level block. Files that do not parse, and other languages
  (JS/TS/Go/Rust/…), fall back to regex boundaries. YAML/TOML/INI files are cut per
  top-level block and Markdown per heading. Chunks partition the file, so the *Files*
  tab can show every boundary.
* **Local embeddings** ([`embedder.py`](p1/ioc_index/embedder.py)) use `all-MiniLM-L6-v2` in its ONNX build (no
  PyTorch). It is downloaded once to `IOC_EMBED_CACHE`, then never fetched again.
* **Persistent store** ([`store.py`](p1/ioc_index/store.py)) is a ChromaDB `PersistentClient`, one collection
  using cosine distance. Each chunk carries `path`, `start_line`, `end_line`, `kind`,
  `symbol`, `signature`, `hash` and `file_hash`.
* **Incremental reindex** ([`indexer.py`](p1/ioc_index/indexer.py)):
  * Chunk ids are stable (`path + kind + symbol + occurrence`).
  * A file is re-chunked only if its sha256 changed.
  * Inside it, only chunks whose own hash changed are re-embedded.
  * Chunks that just moved get a metadata-only update.
  * Deleting a file (or a directory) removes exactly its chunks.
  * A restart re-embeds nothing.
* **Watcher** ([`watcher.py`](p1/ioc_index/watcher.py)) uses watchdog with a debounce. `IOC_WATCH_MODE=auto` tries
  inotify and falls back to polling. Docker uses `polling`, because inotify drops
  events on bind mounts. A reconcile pass every 5 s compares `(mtime, size)`, so a
  missed event is still picked up.
* **Exclusions** ([`walker.py`](p1/ioc_index/walker.py)): the indexer skips
  * `node_modules`, `.git`, `dist`, `build`, `venv`, `.venv` and `__pycache__`;
  * hidden files and directories;
  * binary and oversized files, and `*.ioc.tmp`;
  * the ChromaDB folder and the model cache, even when they live inside the target.

  In Docker, the store lives in `/data/chroma`, outside the target.
* **Dashboard**: *Overview* shows chunk count, target path, Chroma path, models,
  Ollama backend, per-file chunk counts and a live activity feed over SSE. *Files*
  shows real file content with the chunk boundaries marked.
* **API** so far: `GET /status`, `GET /files`, `GET /file?path=…`, `GET /chunks?offset=&limit=&path=&kind=`, `GET /events` (SSE).

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `IOC_TARGET` | `./demo` | target project |
| `IOC_CHROMA_PATH` | `./.ioc-data/chroma` | ChromaDB persist dir (git-ignored) |
| `IOC_EMBED_CACHE` | `~/.cache/chroma/onnx_models` | where the embedding model is cached |
| `IOC_WATCH_MODE` | `auto` | `auto`, `native`, `polling` or `off` |
| `IOC_PORT` | `8000` | HTTP port |

Nothing heavy is committed: model weights, the embedding archive and the ChromaDB
folder are all git-ignored and live in Docker volumes.
