# Layers inside each part, with config and core shared from p1

Each part of the subject (`p1/`, `p2/`, `p3/`) is split by responsibility into the same five layers:
`views` (HTTP routes) → `services` (what the part does) → `repositories` (where its data lives) → `models` (the shape of
its data), plus `schemas` (HTTP request and response bodies, used by `views` only). Inside a part a layer imports only
the layers below it. A part may use an earlier part (`p2` uses `p1`, `p3` uses `p1` and `p2`), never a later one, so each
part can still be started alone for the defense (ADR-0002).

What every part needs lives in `p1/config/settings.py` (every setting) and `p1/core/` (`database.py`, the one Chroma
client of the process, and `llm.py`, the one call to the local model). They sit in `p1` and not at the root because the
subject wants every source file inside `p1`, `p2` or `p3`, and every other part builds on `p1` anyway. They import no
layer. Chroma is imported only in `p1/core/database.py`; each part reads or writes the Index through its own repository (`p1/repositories/chunk_repository.py`
writes and browses, `p2/repositories/search_repository.py` reads for retrieval). `tests/test_layers.py` checks all of this.

Layers are modules of plain functions, not classes, and the models are `TypedDict`s over the same plain dicts as before,
so ADR-0001 (code readable by anyone who has written basic Python) still holds. Settings are read as `settings.NAME` at
call time, never copied with `from config.settings import NAME`, so tests and the console command can change them.

## Considered Options

- `config/` and `core/` at the repository root: the same split, but source files outside `p1`/`p2`/`p3`, against the subject.
- One shared `ioc/` package with all layers, and `p1`/`p2`/`p3` as thin entry points: less repetition of folder names,
  but the parts of the subject no longer hold their own code.
- No layers (the original flat `p1/index.py`, `p2/search.py`, ...): the least code, but the HTTP, logic and storage of a
  part were mixed in one file.
