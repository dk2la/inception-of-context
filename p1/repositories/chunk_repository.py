"""Writing the Index and browsing it: what Part 1 needs from the Chroma collection."""
from p1.core.chroma_db import chroma_db


class ChunkRepository:
    def __init__(self, chroma_db):
        self.chroma_db = chroma_db

    def count(self):
        return self.chroma_db.get_collection().count()

    def metadata_by_id(self, path):
        """{id: metadata} of every Chunk of one file."""
        found = self.chroma_db.get_collection().get(where={"path": path}, include=["metadatas"])
        return dict(zip(found["ids"], found["metadatas"]))

    def all_metadata(self):
        """The metadata of every Chunk in the Index."""
        return self.chroma_db.get_collection().get(include=["metadatas"])["metadatas"]

    def add(self, ids, texts, metadatas):
        self.chroma_db.get_collection().add(ids=ids, documents=texts, metadatas=metadatas)

    def delete(self, ids):
        self.chroma_db.get_collection().delete(ids=ids)

    def update_metadata(self, ids, metadatas):
        self.chroma_db.get_collection().update(ids=ids, metadatas=metadatas)

    def page(self, offset, limit):
        """One page of Chunks: dicts with id, text and the metadata."""
        found = self.chroma_db.get_collection().get(offset=offset, limit=limit, include=["documents", "metadatas"])
        return [dict(meta, id=id_, text=text)
                for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]


chunk_repository = ChunkRepository(chroma_db)
