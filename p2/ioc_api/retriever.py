"""Hybrid retrieval: ChromaDB cosine similarity, re-ranked with an in-memory BM25.

Embeddings are good at paraphrased intent and weak at exact identifiers
("where is authenticate used?"). BM25 over identifier-aware tokens fixes the
latter. ChromaDB stays the canonical store; BM25 is rebuilt from it whenever
the collection changes.
"""
from __future__ import annotations

import re
import threading

from rank_bm25 import BM25Okapi

from ioc_index.embedder import Embedder
from ioc_index.store import Store

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_STOP = {"the", "a", "an", "is", "of", "to", "in", "and", "or", "for", "on", "it", "this", "that", "how",
         "what", "where", "which", "does", "do", "with", "be", "are", "self", "return", "def", "import",
         "from", "as", "none", "true", "false", "if", "else", "not"}


def tokenize(text: str) -> list[str]:
    """Identifier-aware tokens: `NoteService.by_tag` -> noteservice, note, service, by_tag, by, tag."""
    out: list[str] = []
    for ident in _IDENT.findall(text):
        low = ident.lower()
        if low not in _STOP:
            out.append(low)
        parts = [p.lower() for piece in ident.split("_") for p in _CAMEL.findall(piece)]
        if len(parts) > 1:
            out.extend(p for p in parts if len(p) > 1 and p not in _STOP)
    return out


class Retriever:
    def __init__(self, store: Store, embedder: Embedder, alpha: float = 0.6) -> None:
        self.store = store
        self.embedder = embedder
        self.alpha = alpha                      # weight of the vector score in the final blend
        self._lock = threading.Lock()
        self._version = -1
        self._bm25: BM25Okapi | None = None
        self._rows: list[tuple[str, str, dict]] = []

    def _ensure_bm25(self) -> None:
        with self._lock:
            if self._version == self.store.version and self._bm25 is not None:
                return
            rows = self.store.all_documents()
            corpus = [tokenize(f"{m['path']} {m['symbol']} {d}") or ["_"] for _, d, m in rows]
            self._bm25 = BM25Okapi(corpus) if corpus else None
            self._rows = rows
            self._version = self.store.version

    def search(self, query: str, k: int = 5, path: str | None = None) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        k = max(1, min(int(k), 50))
        self._ensure_bm25()
        if not self._rows:
            return []
        where = {"path": path} if path else None
        # The index of a small target is small: score every chunk on both axes.
        n = min(len(self._rows), max(k * 8, 200))
        vec_hits = self.store.query(self.embedder.embed_one(query), n=n, where=where)
        vec = {h["id"]: h["score"] for h in vec_hits}

        bm = {}
        if self._bm25 is not None:
            q_tokens = tokenize(query)
            if q_tokens:
                scores = self._bm25.get_scores(q_tokens)
                top = max(scores) if len(scores) else 0.0
                if top > 0:
                    bm = {self._rows[i][0]: float(s) / top for i, s in enumerate(scores) if s > 0}

        by_id = {i: (d, m) for i, d, m in self._rows}
        candidates = set(vec) | {i for i in bm if not path or by_id[i][1]["path"] == path}
        floor = min(vec.values()) if vec else 0.0
        hits = []
        for cid in candidates:
            if cid not in by_id:
                continue
            doc, meta = by_id[cid]
            v = vec.get(cid, floor)
            b = bm.get(cid, 0.0)
            hits.append({
                "id": cid, "path": meta["path"], "start_line": meta["start_line"], "end_line": meta["end_line"],
                "kind": meta["kind"], "symbol": meta["symbol"], "text": doc,
                "score": round(self.alpha * v + (1 - self.alpha) * b, 4),
                "vector_score": round(v, 4), "bm25_score": round(b, 4),
            })
        hits.sort(key=lambda h: (-h["score"], h["path"], h["start_line"]))
        return hits[:k]
