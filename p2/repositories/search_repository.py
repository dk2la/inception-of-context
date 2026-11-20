"""Reading the Index for retrieval and answers: what Part 2 needs from the Chroma collection."""
from p1.core.database import get_collection


def rank_by_meaning(query):
    """Every Chunk ranked by vector similarity to the query. Return (ids best first, {id: similarity})."""
    collection = get_collection()
    if collection.count() == 0:
        return [], {}  # Chroma refuses to return 0 results
    result = collection.query(query_texts=[query], n_results=collection.count())
    ids = result["ids"][0]
    return ids, {i: 1 - d for i, d in zip(ids, result["distances"][0])}


def all_texts():
    """(ids, texts) of every Chunk in the Index, in the same order."""
    stored = get_collection().get(include=["documents"])
    return stored["ids"], stored["documents"]


def get_many(ids):
    """{id: (text, metadata)} for these ids. Chroma may return them in any order."""
    found = get_collection().get(ids=ids)
    return dict(zip(found["ids"], zip(found["documents"], found["metadatas"])))


def of_kinds(kinds):
    """Chunk dicts (the metadata plus "id" and "text") of every Chunk of these kinds."""
    found = get_collection().get(where={"kind": {"$in": kinds}})
    return [dict(meta, id=id_, text=text) for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]


def metadata_of_file(path):
    """The metadata of every Chunk of one file."""
    return get_collection().get(where={"path": path}, include=["metadatas"])["metadatas"]
