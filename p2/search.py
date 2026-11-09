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


def bm25_search(query):
    """Rank every Chunk by keywords (BM25). Return the ids, best first."""
    stored = index.get_collection().get()
    if not stored["ids"]:
        return []  # BM25Okapi fails on no documents
    bm25 = BM25Okapi([tokenize(text) for text in stored["documents"]])
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(stored["ids"], scores), key=lambda pair: pair[1], reverse=True)
    return [chunk_id for chunk_id, _ in ranked]
