# One process, with p1 → p2 → p3 layered by import

The subject requires separate `p1`, `p2`, `p3` folders and one Chroma client per process. Each part imports the previous one instead of copying it (`p2` imports `p1`; `p3` imports the `p2` app and adds `/patch`), so no code exists twice, and each part can still be started alone for the defense. The Watcher runs as a background thread inside the API server process rather than as its own container, because two processes writing to the same Chroma directory (SQLite underneath) invite locking problems.

## Considered Options

- Each folder a full standalone copy of the previous one: fully independent folders, but duplicated code that drifts.
- Watcher in a separate container: cleaner separation, but two writers on one Chroma directory.
