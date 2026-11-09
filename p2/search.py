"""Retrieval: rank the whole Index by meaning and by keywords, then merge the two rankings."""
import re

from rank_bm25 import BM25Okapi

from p1 import index


def tokenize(text):
    """Lowercase words and numbers. Punctuation and underscores split words: divide_by_zero -> 3 words."""
    return re.findall(r"[a-z0-9]+", text.lower())


def vector_search(query):
    """Rank every Chunk by meaning. Return (ids best first, {id: similarity})."""
    collection = index.get_collection()
    if collection.count() == 0:
        return [], {}  # Chroma refuses to return 0 results
    result = collection.query(query_texts=[query], n_results=collection.count())
    ids = result["ids"][0]
    similarity = {i: 1 - d for i, d in zip(ids, result["distances"][0])}
    return ids, similarity


_bm25 = None  # the BM25Okapi object, or None when the Index is empty
_bm25_ids = []  # Chunk ids, in the same order as the documents of _bm25
_bm25_version = -1  # the INDEX_VERSION they were built from; -1 = never built
_bm25_collection = None  # the collection they were built from (a different Index must not reuse them)


def _build_bm25(collection):
    """Read every Chunk from the Index and build the BM25 index from them."""
    global _bm25, _bm25_ids, _bm25_version, _bm25_collection
    stored = collection.get()
    _bm25_ids = stored["ids"]
    _bm25 = BM25Okapi([tokenize(text) for text in stored["documents"]]) if _bm25_ids else None  # it fails on no documents
    _bm25_version = index.INDEX_VERSION
    _bm25_collection = collection


def bm25_search(query):
    """Rank every Chunk by keywords (BM25). Return the ids, best first. The BM25 index is rebuilt only after the Index changed."""
    collection = index.get_collection()
    if index.INDEX_VERSION != _bm25_version or collection is not _bm25_collection:
        _build_bm25(collection)
    if _bm25 is None:
        return []
    scores = _bm25.get_scores(tokenize(query))
    ranked = sorted(zip(_bm25_ids, scores), key=lambda pair: pair[1], reverse=True)
    return [chunk_id for chunk_id, _ in ranked]


def rrf_merge(ranked_a, ranked_b, k=60):
    """Reciprocal Rank Fusion: add 1 / (k + rank) for every list an id appears in. Return {id: score}."""
    scores = {}
    for ranked in (ranked_a, ranked_b):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)
    return scores
