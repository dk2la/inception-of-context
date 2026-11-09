"""Retrieval: rank the whole Index by meaning and by keywords, then merge the two rankings."""
import re

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
