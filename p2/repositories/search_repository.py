"""Reading the Index for retrieval and answers: what Part 2 needs from the Chroma collection."""
from p1.core.chroma_db import chroma_db


class SearchRepository:
    def __init__(self, chroma_db):
        # debug: chroma_db is the ChromaDB object. This repository only reads the collection.
        self.chroma_db = chroma_db

    def rank_by_meaning(self, query):
        """Every Chunk ranked by vector similarity to the query. Return (ids best first, {id: similarity})."""
        # debug: query == "division by zero". Chroma embeds it with all-MiniLM-L6-v2.
        # result["ids"][0] is one list because query_texts has one string. Best match first.
        # result["distances"][0] is cosine distance. similarity == 1 - distance.
        # return == (
        #     ["bb22…", "aa11…"],
        #     {"bb22…": 0.81, "aa11…": 0.22},
        # )  # bb22… is Calculator.divide
        # empty Index: return == ([], {})  # Chroma refuses n_results=0
        collection = self.chroma_db.get_collection()
        if collection.count() == 0:
            return [], {}  # Chroma refuses to return 0 results
        result = collection.query(query_texts=[query], n_results=collection.count())
        ids = result["ids"][0]
        return ids, {i: 1 - d for i, d in zip(ids, result["distances"][0])}

    def all_texts(self):
        """(ids, texts) of every Chunk in the Index, in the same order."""
        # debug: used to build the BM25 index. Two parallel lists, same length.
        # return == (
        #     ["aa11…", "bb22…"],
        #     ["    def add(self, a, b):\n        …", "    def divide(self, a, b):\n        …"],
        # )
        # empty Index: return == ([], [])
        stored = self.chroma_db.get_collection().get(include=["documents"])
        return stored["ids"], stored["documents"]

    def get_many(self, ids):
        """{id: (text, metadata)} for these ids. Chroma may return them in any order."""
        # debug: ids == ["bb22…", "aa11…"]  # the top-k after RRF, best first
        # found["ids"] may come back in another order. zip pairs each id with its own text and metadata.
        # return == {
        #     "bb22…": ("    def divide(self, a, b):\n        …",
        #               {"path": "calculator/core.py", "start_line": 16, "end_line": 20,
        #                "name": "Calculator.divide", "kind": "method", "hash": "…"}),
        #     "aa11…": ("    def add…", {"path": "calculator/core.py", "name": "Calculator.add", …}),
        # }
        found = self.chroma_db.get_collection().get(ids=ids)
        return dict(zip(found["ids"], zip(found["documents"], found["metadatas"])))

    def of_kinds(self, kinds):
        """Chunk dicts (the metadata plus "id" and "text") of every Chunk of these kinds."""
        # debug: kinds == ["function", "async_function", "class", "method"]
        # where == {"kind": {"$in": kinds}}. A class and its methods all match.
        # return == [{
        #     "id": "bb22…", "text": "    def divide…",
        #     "path": "calculator/core.py", "start_line": 16, "end_line": 20,
        #     "name": "Calculator.divide", "kind": "method", "hash": "…",
        # }, ...]
        found = self.chroma_db.get_collection().get(where={"kind": {"$in": kinds}})
        return [dict(meta, id=id_, text=text)
                for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]

    def metadata_of_file(self, path):
        """The metadata of every Chunk of one file."""
        # debug: path == "calculator/core.py". Texts are not loaded.
        # return == [
        #     {"path": "calculator/core.py", "start_line": 1, "end_line": 20,
        #      "name": "Calculator", "kind": "class", "hash": "…"},
        #     {"path": "calculator/core.py", "start_line": 4, "end_line": 6,
        #      "name": "Calculator.add", "kind": "method", "hash": "…"},
        #     … subtract, multiply, divide …
        # ]
        return self.chroma_db.get_collection().get(where={"path": path}, include=["metadatas"])["metadatas"]


search_repository = SearchRepository(chroma_db)
