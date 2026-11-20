"""Retrieval: rank the whole Index by meaning and by keywords, then merge the two rankings."""
import re

from rank_bm25 import BM25Okapi

from p1.config import settings
from p1.core import database
from p2.repositories import search_repository


def tokenize(text):
    """Lowercase words and numbers. Punctuation and underscores split words: divide_by_zero -> 3 words."""
    return re.findall(r"[a-z0-9]+", text.lower())


def vector_search(query):
    """Rank every Chunk by meaning. Return (ids best first, {id: similarity})."""
    return search_repository.rank_by_meaning(query)


_bm25 = None  # the BM25Okapi object, or None when the Index is empty
_bm25_ids = []  # Chunk ids, in the same order as the documents of _bm25
_bm25_version = -1  # the INDEX_VERSION they were built from; -1 = never built
_bm25_collection = None  # the collection they were built from (a different Index must not reuse them)


def _build_bm25(collection):
    """Read every Chunk from the Index and build the BM25 index from them."""
    global _bm25, _bm25_ids, _bm25_version, _bm25_collection
    # The version is read BEFORE the texts: if the Watcher changes the Index in between, this BM25 index
    # is marked older than the Index and is rebuilt on the next search, instead of staying stale.
    version = database.INDEX_VERSION
    ids, texts = search_repository.all_texts()
    bm25 = BM25Okapi([tokenize(text) for text in texts]) if ids else None  # BM25Okapi fails on no documents
    _bm25, _bm25_ids = bm25, ids  # set together, so a search in another thread never mixes two builds
    _bm25_version = version
    _bm25_collection = collection


def bm25_search(query):
    """Rank every Chunk by keywords (BM25). Return the ids, best first.

    The BM25 index is rebuilt only when the Index changed (a new version, or another Index).
    """
    collection = database.get_collection()
    if database.INDEX_VERSION != _bm25_version or collection is not _bm25_collection:
        _build_bm25(collection)
    bm25, ids = _bm25, _bm25_ids  # one consistent pair, even if another thread rebuilds meanwhile
    if bm25 is None:
        return []
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(ids, scores), key=lambda pair: pair[1], reverse=True)
    return [chunk_id for chunk_id, _ in ranked]


def rrf_merge(ranked_a, ranked_b):
    """Reciprocal Rank Fusion: add 1 / (RRF_K + rank) for every list an id appears in. Return {id: score}."""
    scores = {}
    for ranked in (ranked_a, ranked_b):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (settings.RRF_K + rank)
    return scores


def search(query, k):
    """The top k Chunks for a query, best first: the Chunk fields plus id, text, similarity and score."""
    vector_ids, similarity = vector_search(query)
    scores = rrf_merge(vector_ids, bm25_search(query))
    top_ids = sorted(scores, key=scores.get, reverse=True)[:max(k, 0)]
    if not top_ids:
        return []  # empty Index or k <= 0; Chroma refuses to get no ids

    by_id = search_repository.get_many(top_ids)
    results = []
    for chunk_id in top_ids:
        if chunk_id not in by_id:
            continue  # the Watcher deleted it after it was ranked (a file changed during this search)
        text, metadata = by_id[chunk_id]
        results.append({**metadata, "id": chunk_id, "text": text,
                        "similarity": similarity.get(chunk_id, 0.0), "score": scores[chunk_id]})
    return results
