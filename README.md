# Inception-of-Context (IoC)

A local, self-hosted coding assistant: it indexes a codebase into a vector
store, answers questions about it with a small local model, and turns a
textual intent into a validated patch that rolls back on failure.
**Everything runs locally**: no remote LLM is ever called.

| Part | Folder | What it does |
|---|---|---|
| 1 | [`p1/`](p1) | Logical chunking (AST), local embeddings (all-MiniLM-L6-v2), persistent ChromaDB, incremental watcher, dashboard *Overview* + *Files* |
| 2 | [`p2/`](p2) | Architect API (FastAPI): `/context` hybrid retrieval (Chroma + BM25), `/ask` grounded Q&A with a local `qwen2.5:3b`, dashboard *ChromaDB Explorer* + *Ask & Retrieve* |
| — | [`demo/`](demo) | The target project: a tiny notes app with its own `ioc.config.yml` |

## Quick start

Requirements: Docker with Compose v2, `make`, ~6 GB free disk and ~8 GB RAM (two 3B models).
A GPU is optional; on CPU an answer takes a few seconds to a few tens of seconds.

```bash
make up          # build + start, then open http://localhost:8000
make logs        # follow what the indexer / watcher does
make down        # stop (index and cached model are kept in a volume)
make clean       # stop and delete the index + cached model
```

The stack has three services:
* `ollama` is the local model server.
* `models` is a one-shot container. It pulls `qwen2.5:3b` and `qwen2.5-coder:3b` the
  first time, then only checks that they are present.
* `ioc` runs the indexer, watcher, API and dashboard.

The first start downloads the LLMs (~1.9 GB each) and the embedding model
(`all-MiniLM-L6-v2`, ~80 MB) into Docker volumes. Every later start is offline.
`IOC_PART=p1 make up` runs only part 1.

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

## Part 2: Architect API and RAG

`python p2/serve.py [target]` runs part 1 (indexer + watcher) plus the API, in
one process that shares one ChromaDB client.

| Endpoint | What |
|---|---|
| `GET /status`, `GET /files`, `GET /file?path=`, `GET /chunks` | index state (from part 1) |
| `GET /events` | file events, Server-Sent Events |
| `POST /context` `{query, k, path?}` | top-k chunks with `score`, `vector_score` and `bm25_score` |
| `POST /ask` `{question, k, session_id?}` | retrieve, then generate a grounded answer, with its sources |
| `GET /symbols?path=` | every function / method / class the index knows |
| `GET /llm/health` | is Ollama up, which models are pulled |

* **Hybrid retrieval** ([`retriever.py`](p2/ioc_api/retriever.py)):
  * Cosine similarity comes from ChromaDB.
  * BM25 (`rank_bm25`) runs in memory over identifier-aware tokens:
    `NoteService.by_tag` becomes `noteservice, note, service, by_tag, tag`.
  * Final score: `0.6·vector + 0.4·bm25_normalized`.
  * The BM25 index is rebuilt whenever the collection changes. ChromaDB stays the
    single source of truth.
* **No hallucinated symbols** ([`symbols.py`](p2/ioc_api/symbols.py), [`ask.py`](p2/ioc_api/ask.py)). The index knows exactly which
  symbols exist, so this knowledge is resolved *before* the model is allowed to speak:
  * *“is there a function X?”*, *“what functions are in file Y?”* and *“where is X
    defined?”* are answered directly from the index, without the LLM, in English or
    Russian. The answer is exact, including “No, `X` does not exist; closest names: …”.
  * *“where is X used?”*: the exact usage list comes from the index, and the model only
    adds an explanation.
  * Any other question goes through RAG. The prompt gets the top-k snippets plus
    **symbol facts**: every identifier from the question is checked against the
    index (“`authenticate` does NOT exist”). A missing symbol is also stated
    deterministically at the top of the answer.
  * After generation, any `name()` the answer mentions that appears neither in the index
    nor in the snippets is flagged as unverified.
* Sessions: `session_id` keeps the last 3 Q/A turns. *New conversation* resets it.
* If Ollama is down, `/ask` returns a clean `503`; symbol questions still work.

Dashboard: *ChromaDB Explorer* (raw chunks, filter by file/kind, pagination) and
*Ask & Retrieve* (question, `k`, Retrieve only or Ask LLM, answer + ranked sources).

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | local Ollama |
| `IOC_ASK_MODEL` | `qwen2.5:3b` | model for `/ask` |
| `IOC_CODE_MODEL` | `qwen2.5-coder:3b` | model for the patch loop (part 3) |
