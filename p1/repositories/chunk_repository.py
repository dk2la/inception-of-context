"""Writing the Index and browsing it: what Part 1 needs from the Chroma collection."""
from p1.core.database import get_collection


def count():
    return get_collection().count()


def metadata_by_id(path):
    """{id: metadata} of every Chunk of one file."""
    found = get_collection().get(where={"path": path}, include=["metadatas"])
    return dict(zip(found["ids"], found["metadatas"]))


def all_metadata():
    """The metadata of every Chunk in the Index."""
    return get_collection().get(include=["metadatas"])["metadatas"]


def add(ids, texts, metadatas):
    get_collection().add(ids=ids, documents=texts, metadatas=metadatas)


def delete(ids):
    get_collection().delete(ids=ids)


def update_metadata(ids, metadatas):
    get_collection().update(ids=ids, metadatas=metadatas)


def page(offset, limit):
    """One page of Chunks: dicts with id, text and the metadata."""
    found = get_collection().get(offset=offset, limit=limit, include=["documents", "metadatas"])
    return [dict(meta, id=id_, text=text) for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]
