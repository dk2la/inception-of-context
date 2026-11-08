"""Local embeddings. Default: all-MiniLM-L6-v2 (ONNX build shipped by ChromaDB, no torch).

The model archive (~80 MB) is downloaded once into the cache folder; every
later run loads it from disk and never touches the network.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path


class Embedder:
    name = "base"
    dim = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OnnxMiniLM(Embedder):
    name = "all-MiniLM-L6-v2"
    dim = 384

    def __init__(self, cache_dir: Path | None = None) -> None:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        self._ef = ONNXMiniLM_L6_V2()
        if cache_dir is not None:
            self._ef.DOWNLOAD_PATH = str(Path(cache_dir) / "all-MiniLM-L6-v2")
        self.cache_dir = Path(self._ef.DOWNLOAD_PATH)

    @property
    def is_downloaded(self) -> bool:
        return (self.cache_dir / "onnx" / "model.onnx").exists()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out = self._ef(texts)
        return [[float(x) for x in vec] for vec in out]


class FakeEmbedder(Embedder):
    """Deterministic hashed bag-of-words. Only for tests and machines without the model."""

    name = "fake-hash-256"
    dim = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in re.findall(r"[A-Za-z_]\w*", text.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


def make_embedder(kind: str, cache_dir: Path | None = None) -> Embedder:
    if kind == "fake":
        return FakeEmbedder()
    return OnnxMiniLM(cache_dir)


def embedding_text(path: str, symbol: str, kind: str, text: str) -> str:
    """What actually gets embedded: location + symbol help paraphrased queries land."""
    return f"{path} {kind} {symbol}\n{text}"
