"""Thin wrapper around a persistent ChromaDB collection (one client per process)."""
from __future__ import annotations

import threading
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class Store:
    def __init__(self, path: Path, collection: str = "ioc", embed_model: str = "") -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
        self.collection_name = collection
        self.col = self.client.get_or_create_collection(
            name=collection, embedding_function=None,
            metadata={"hnsw:space": "cosine", "embed_model": embed_model or "unknown"})
        self.version = 0                       # bumped on every write (BM25 cache key)
        self._lock = threading.RLock()

    # -- writes -------------------------------------------------------------
    def upsert(self, ids, documents, metadatas, embeddings) -> None:
        if not ids:
            return
        with self._lock:
            self.col.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
            self.version += 1

    def update_metadata(self, ids, metadatas) -> None:
        if not ids:
            return
        with self._lock:
            self.col.update(ids=ids, metadatas=metadatas)
            self.version += 1

    def delete_ids(self, ids) -> None:
        if not ids:
            return
        with self._lock:
            self.col.delete(ids=list(ids))
            self.version += 1

    def delete_path(self, path: str) -> int:
        ids = list(self.file_chunks(path))
        self.delete_ids(ids)
        return len(ids)

    def reset(self) -> None:
        with self._lock:
            self.client.delete_collection(self.collection_name)
            self.col = self.client.get_or_create_collection(
                name=self.collection_name, embedding_function=None, metadata={"hnsw:space": "cosine"})
            self.version += 1

    # -- reads --------------------------------------------------------------
    def count(self) -> int:
        return self.col.count()

    def file_chunks(self, path: str) -> dict[str, dict]:
        res = self.col.get(where={"path": path}, include=["metadatas"])
        return dict(zip(res["ids"], res["metadatas"]))

    def all_metadata(self) -> list[tuple[str, dict]]:
        res = self.col.get(include=["metadatas"])
        return list(zip(res["ids"], res["metadatas"]))

    def all_documents(self) -> list[tuple[str, str, dict]]:
        res = self.col.get(include=["documents", "metadatas"])
        return list(zip(res["ids"], res["documents"], res["metadatas"]))

    def all_paths(self) -> set[str]:
        return {m["path"] for _, m in self.all_metadata()}

    def page(self, offset: int, limit: int, where: dict | None = None) -> tuple[int, list[dict]]:
        res = self.col.get(where=where, include=["documents", "metadatas"])
        rows = [{"id": i, "document": d, "metadata": m}
                for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]
        rows.sort(key=lambda r: (r["metadata"]["path"], r["metadata"]["start_line"]))
        return len(rows), rows[offset:offset + limit]

    def get(self, ids: list[str]) -> list[dict]:
        res = self.col.get(ids=ids, include=["documents", "metadatas"])
        return [{"id": i, "document": d, "metadata": m}
                for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]

    def query(self, embedding: list[float], n: int, where: dict | None = None) -> list[dict]:
        total = self.count()
        if total == 0:
            return []
        res = self.col.query(query_embeddings=[embedding], n_results=max(1, min(n, total)), where=where,
                             include=["documents", "metadatas", "distances"])
        return [{"id": i, "document": d, "metadata": m, "distance": dist, "score": 1.0 - dist}
                for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                          res["distances"][0])]
