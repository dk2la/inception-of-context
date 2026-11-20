"""Reading the Index for retrieval and answers: what Part 2 needs from the Chroma collection."""
from p1.core.chroma_db import chroma_db


class SearchRepository:
    def __init__(self, chroma_db):
        self.chroma_db = chroma_db

    def rank_by_meaning(self, query):
        """Every Chunk ranked by vector similarity to the query. Return (ids best first, {id: similarity})."""
        collection = self.chroma_db.get_collection()
        if collection.count() == 0:
            return [], {}  # Chroma refuses to return 0 results
        result = collection.query(query_texts=[query], n_results=collection.count())
        ids = result["ids"][0]
        return ids, {i: 1 - d for i, d in zip(ids, result["distances"][0])}

    def all_texts(self):
        """(ids, texts) of every Chunk in the Index, in the same order."""
        stored = self.chroma_db.get_collection().get(include=["documents"])
        return stored["ids"], stored["documents"]

    def get_many(self, ids):
        """{id: (text, metadata)} for these ids. Chroma may return them in any order."""
        found = self.chroma_db.get_collection().get(ids=ids)
        return dict(zip(found["ids"], zip(found["documents"], found["metadatas"])))

    def of_kinds(self, kinds):
        """Chunk dicts (the metadata plus "id" and "text") of every Chunk of these kinds."""
        found = self.chroma_db.get_collection().get(where={"kind": {"$in": kinds}})
        return [dict(meta, id=id_, text=text) for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]

    def metadata_of_file(self, path):
        """The metadata of every Chunk of one file."""
        return self.chroma_db.get_collection().get(where={"path": path}, include=["metadatas"])["metadatas"]


search_repository = SearchRepository(chroma_db)
