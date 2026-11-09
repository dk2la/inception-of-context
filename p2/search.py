"""Retrieval: rank the whole Index by meaning and by keywords, then merge the two rankings."""
from p1 import index


def vector_search(query):
    """Rank every Chunk by meaning. Return (ids best first, {id: similarity})."""
    collection = index.get_collection()
    if collection.count() == 0:
        return [], {}  # Chroma refuses to return 0 results
    result = collection.query(query_texts=[query], n_results=collection.count())
    ids = result["ids"][0]
    similarity = {i: 1 - d for i, d in zip(ids, result["distances"][0])}
    return ids, similarity
