# Inception-of-Context (IoC)

A local, self-hosted coding assistant: it indexes a codebase into a vector
store, answers questions about it with a small local model, and turns a
textual intent into a validated patch that rolls back on failure.
**Everything runs locally**: no remote LLM is ever called.

| Part | Folder | What it does |
|---|---|---|
| 1 | [`p1/`](p1) | Logical chunking (AST), local embeddings (all-MiniLM-L6-v2), persistent ChromaDB, incremental watcher, dashboard *Overview* + *Files* |
| 2 | [`p2/`](p2) | Architect API (FastAPI): `/context` hybrid retrieval (Chroma + BM25), `/ask` grounded Q&A with a local `qwen2.5:3b`, dashboard *ChromaDB Explorer* + *Ask & Retrieve* |
| 3 | [`p3/`](p3) | Patch loop: `qwen2.5-coder:3b` writes a JSON patch, which is sanity-checked, applied atomically, validated by `ioc.config.yml`, retried up to 3 times, then committed or rolled back byte-for-byte. Dashboard *Patch Loop* |
| ★ | [`bonus/`](bonus) | `POST /reindex`, dry-run diffs, auto `git commit` with a model-written message, visual diff + git log tab |
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
By default `make up` runs the full system (part 3). `IOC_PART=p1 make up` or `IOC_PART=p2 make up` runs an earlier stage.

### Demo script (≈5 minutes)

1. Open **Overview** for the chunk count, models and indexed files. **Files** shows the chunk
   boundaries; open `notes/service.py` and each method is its own chunk.
2. Edit `demo/notes/service.py` in an editor: the *Live activity* feed shows `modified … updated=1`.
   Delete a file: `deleted … removed=N`.
3. **Ask & Retrieve**:
   * `is there a function called authenticate?` → "No …", answered from the index.
   * `what functions are in notes/service.py?` → the exact list.
   * `explain how NoteService.search works` → a grounded answer with its sources.
4. **Patch Loop**: `add a function whisper(name) in main.py that returns the greeting in lowercase`
   → `SUCCESS in 1 attempt(s)`, and the watcher reindexes `main.py`.
5. Force a rollback: `change greet in main.py so it returns 'Hi, {name}!'. Do not touch the tests.`
   The test suite fails three times, the project is restored byte-for-byte and `git status demo` is clean.
6. `make reset-demo` puts the demo back after successful patches.

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

## Part 3: generation, application and validation loop

`python p3/serve.py [target]` runs the full system. A loop iteration is driven from the
*Patch Loop* tab or over HTTP:

| Endpoint | What |
|---|---|
| `POST /patch/run` `{intent, k, max_attempts≤3, stream?}` | the full loop. `stream: true` returns NDJSON step events (used by the dashboard) |
| `POST /patch/generate` `{intent, k}` | a single stage: generate + sanity check, nothing is written |
| `GET /patch/history` | the last 20 runs |

**Patch format**: structured JSON, never a diff. `content` is the complete post-change file:

```json
{"summary": "add whisper() to main.py",
 "files": [{"path": "main.py", "op": "modify", "content": "<complete new file>"}]}
```

**One iteration** ([`loop.py`](p3/ioc_patch/loop.py)):
1. **Generate** ([`generator.py`](p3/ioc_patch/generator.py)): `qwen2.5-coder:3b` runs in Ollama's JSON mode. The prompt holds
   * the intent;
   * the project file list;
   * symbol facts from part 2;
   * the *full* content of up to 3 relevant files (files named in the intent first, then the files of the top-k chunks);
   * the other retrieved chunks as read-only context.

   On a retry the prompt also gets the previous answer and the exact error.
2. **Sanity** ([`sanity.py`](p3/ioc_patch/sanity.py)): hard refusals before any write. A patch is rejected if it
   * leaks retrieval/prompt markers (`<<<IOC_…>>>`, `### [`, code fences);
   * `create`s an existing file, or `modify`/`delete`s a missing one;
   * replaces a non-empty file with `""`, `"None"` or `"null"`;
   * adds a function whose body is only `pass`, `...`, `return None` or `raise NotImplementedError`
     (checked with the AST; stubs that already existed are tolerated);
   * shrinks a file by more than 60 %;
   * touches more than 3 files;
   * writes outside the target, into hidden/vendor folders, or leaves a `modify` with no change.
3. **Apply** ([`applier.py`](p3/ioc_patch/applier.py)):
   * Every touched file is snapshotted *before the first write of the loop*: its bytes and mode, or the fact that it did not exist.
   * Each change is written to `<file>.ioc.tmp`. Only once all of them are staged are they `os.replace`d into place.
4. **Validate** ([`validator.py`](p3/ioc_patch/validator.py)): runs `validate.command` from `<target>/ioc.config.yml`.
   * `{files}` and `{py_files}` are replaced by the touched files.
   * The default is `python -m py_compile {py_files}`.
   * A list of commands runs as a chain.
   * Bytecode goes to a temp prefix, so validation never writes `__pycache__` into the target.
5. **Green**: the patch stays and the touched files are reindexed silently.
   **Red**: the snapshot is restored and the validation log goes back to the model. After **3** failed
   iterations the project is restored to its exact pre-loop state: created files and directories are
   removed, deleted files are restored, and the restore is verified by hash (`rollback_verified: true`).

Only one loop runs at a time (`409` otherwise). If the model is unreachable, the loop
stops with `status: error` and nothing changes.

`demo/ioc.config.yml`:

```yaml
validate:
  command: "python -m py_compile {py_files} && python -m pytest -q -p no:cacheprovider tests"
  timeout: 120
```

### Tested with the real models (CPU, no GPU)

| Intent | Result |
|---|---|
| add a function whisper(name) in main.py that returns the greeting in lowercase | success, 1 attempt, ~25 s |
| add a method count() to NoteService that returns the number of stored notes | success, 1 attempt, ~50 s |
| rename the function shout to yell everywhere | success, 1 attempt (main.py + tests), ~70 s |
| change greet to return 'Hi, {name}!', do not touch the tests | 3 failed validations → rolled back, tree identical |

A 3B model sometimes rewrites untouched lines (quote style, the module docstring). The loop
only guarantees that the result compiles and passes the configured validation.

## Bonus

`python bonus/serve.py [target]` (or `make bonus`) runs the full system plus:

* **`POST /reindex[?reset=true]`**: an on-demand reindex. It is incremental by default;
  `reset=true` drops the collection and re-embeds everything.
* **Dry-run mode**: `POST /patch/dry-run {intent, k}` generates and sanity-checks a patch
  and returns a unified diff per file. The disk is never touched.
* **Auto git commit** (`IOC_AUTOCOMMIT=1`): every validated patch is committed in the
  target repository, with a one-line message written by the local model from the patch
  summary. If the target is not the root of a git repository, the commit is skipped and
  the reason is reported.
  * `make bonus` creates `.ioc-data/demo-repo`, a git copy of `demo/` (git-ignored), and starts
    the stack on it with auto-commit enabled.
* **Richer dashboard**: the *Diff & Git* tab shows
  * a dry-run with a coloured diff;
  * the diff of the last committed patch and its commit;
  * reindex buttons and the target's git log.

  Patch-loop steps already stream live (NDJSON), and validation results are pushed to the
  SSE activity feed.

Not implemented: the Docker SDK log watcher. It would need the Docker socket mounted into the
container, i.e. root on the host, which defeats the isolation the subject asks for.
