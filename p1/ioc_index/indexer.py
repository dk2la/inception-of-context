"""Incremental indexer: keeps the ChromaDB collection a mirror of the target on disk.

* A file is re-chunked only when its content hash changes.
* Inside a changed file, only chunks whose own hash changed are re-embedded;
  chunks that merely moved (line numbers) get a metadata-only update.
* Deleting a file deletes exactly its chunks.
"""
from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

from .chunker import Chunk, chunk_file
from .config import Settings
from .embedder import Embedder, embedding_text
from .events import EventBus
from .store import Store
from .walker import FileFilter, read_text


def chunk_id(path: str, kind: str, symbol: str, occurrence: int) -> str:
    raw = f"{path}\0{kind}\0{symbol}\0{occurrence}".encode()
    return hashlib.sha1(raw).hexdigest()[:24]


def chunk_metadata(c: Chunk, file_hash: str) -> dict:
    return {
        "path": c.path, "start_line": c.start_line, "end_line": c.end_line, "kind": c.kind,
        "symbol": c.symbol, "name": c.name, "signature": c.signature, "language": c.language,
        "hash": c.hash, "file_hash": file_hash,
    }


class Indexer:
    def __init__(self, settings: Settings, store: Store, embedder: Embedder, events: EventBus) -> None:
        self.settings = settings
        self.store = store
        self.embedder = embedder
        self.events = events
        excluded = [settings.chroma_path]
        if settings.embed_cache:
            excluded.append(settings.embed_cache)
        self.filter = FileFilter(settings.target, excluded=excluded, max_bytes=settings.max_file_bytes)
        self.lock = threading.RLock()
        self._file_hashes: dict[str, str] = {}
        self.state = "idle"
        self.last_sync: float | None = None

    # ------------------------------------------------------------------ public
    def full_sync(self, quiet: bool = False) -> dict:
        """Bring the collection in line with the disk (cheap when nothing changed)."""
        with self.lock:
            self.state = "indexing"
            t0 = time.time()
            totals = {"files": 0, "added": 0, "updated": 0, "moved": 0, "removed": 0, "unchanged": 0}
            on_disk = list(self.filter.walk())
            for rel in on_disk:
                res = self.index_file(rel, reason="scan", publish=False)
                totals["files"] += 1
                if res:
                    for k in ("added", "updated", "moved", "removed", "unchanged"):
                        totals[k] += res[k]
            stale = self.store.all_paths() - set(on_disk)
            for rel in sorted(stale):
                totals["removed"] += self.remove_file(rel, publish=False)
            self.state = "ready"
            self.last_sync = time.time()
            totals["chunks"] = self.store.count()
            totals["seconds"] = round(time.time() - t0, 2)
            if not quiet:
                self.events.publish("sync", **totals)
            return totals

    def index_file(self, rel: str, reason: str = "modified", publish: bool = True) -> dict | None:
        """(Re)index one file. Returns a stats dict, or None when the content did not change."""
        with self.lock:
            full = self.settings.target / rel
            text = read_text(full)
            fhash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            existing = self.store.file_chunks(rel)
            if self._file_hashes.get(rel) == fhash and existing:
                return None
            if existing and all(m.get("file_hash") == fhash for m in existing.values()):
                self._file_hashes[rel] = fhash
                return {"path": rel, "added": 0, "updated": 0, "moved": 0, "removed": 0,
                        "unchanged": len(existing), "chunks": len(existing)}

            chunks = chunk_file(rel, text)
            seen: dict[tuple[str, str], int] = {}
            new: dict[str, tuple[Chunk, dict]] = {}
            for c in chunks:
                key = (c.kind, c.symbol)
                seen[key] = seen.get(key, 0) + 1
                cid = chunk_id(rel, c.kind, c.symbol, seen[key])
                new[cid] = (c, chunk_metadata(c, fhash))

            to_embed = [cid for cid, (c, _) in new.items()
                        if cid not in existing or existing[cid].get("hash") != c.hash]
            to_move = [cid for cid in new if cid in existing and cid not in to_embed]
            to_delete = [cid for cid in existing if cid not in new]

            if to_embed:
                docs = [new[cid][0].text for cid in to_embed]
                vectors = self.embedder.embed([
                    embedding_text(rel, new[cid][0].symbol, new[cid][0].kind, new[cid][0].text)
                    for cid in to_embed])
                self.store.upsert(to_embed, docs, [new[cid][1] for cid in to_embed], vectors)
            if to_move:
                self.store.update_metadata(to_move, [new[cid][1] for cid in to_move])
            self.store.delete_ids(to_delete)
            self._file_hashes[rel] = fhash

            added = sum(1 for cid in to_embed if cid not in existing)
            stats = {"path": rel, "added": added, "updated": len(to_embed) - added,
                     "moved": sum(1 for cid in to_move
                                  if existing[cid].get("start_line") != new[cid][1]["start_line"]),
                     "removed": len(to_delete),
                     "unchanged": len(to_move), "chunks": len(new)}
            if publish:
                self.events.publish("created" if not existing and reason == "modified" else reason, **stats)
            return stats

    def remove_file(self, rel: str, publish: bool = True) -> int:
        with self.lock:
            removed = self.store.delete_path(rel)
            self._file_hashes.pop(rel, None)
            if publish and removed:
                self.events.publish("deleted", path=rel, removed=removed, chunks=0)
            return removed

    def handle_path(self, path: str | Path) -> None:
        """Entry point for the watcher: figure out what happened to `path` and react."""
        rel = self.filter.rel(path)
        if not rel or self.filter.is_excluded_path(path):
            return
        full = self.settings.target / rel
        with self.lock:
            if full.is_file():
                if self.filter.is_indexable_file(full):
                    self.index_file(rel)
                else:
                    self.remove_file(rel)          # e.g. became binary / too large
            elif full.is_dir():
                for sub in self.filter.walk():
                    if sub.startswith(rel + "/") and sub not in self._file_hashes:
                        self.index_file(sub, reason="created")
            else:
                if rel in self.store.all_paths():
                    self.remove_file(rel)
                else:                              # maybe a whole directory went away
                    for p in sorted(self.store.all_paths()):
                        if p.startswith(rel + "/"):
                            self.remove_file(p)

    # ------------------------------------------------------------------ queries
    def files_overview(self) -> list[dict]:
        counts: dict[str, int] = {}
        for _, m in self.store.all_metadata():
            counts[m["path"]] = counts.get(m["path"], 0) + 1
        out = []
        for rel in self.filter.walk():
            full = self.settings.target / rel
            try:
                size = full.stat().st_size
                n_lines = read_text(full).count("\n") + 1
            except OSError:
                continue
            out.append({"path": rel, "chunks": counts.pop(rel, 0), "bytes": size, "lines": n_lines,
                        "indexed": rel in self._file_hashes or rel in counts})
        for rel, n in counts.items():                   # in the index but gone from disk
            out.append({"path": rel, "chunks": n, "bytes": 0, "lines": 0, "indexed": True, "stale": True})
        return sorted(out, key=lambda f: f["path"])

    def safe_path(self, path: str) -> Path | None:
        """Resolve a user-supplied path inside the target, refusing traversal and excluded files."""
        if not path or "\0" in path:
            return None
        p = Path(path)
        if p.is_absolute():
            return None
        full = (self.settings.target / p).resolve()
        try:
            full.relative_to(self.settings.target)
        except ValueError:
            return None
        if self.filter.is_excluded_path(full):
            return None
        return full
