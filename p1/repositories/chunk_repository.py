"""Writing the Index and browsing it: what Part 1 needs from the Chroma collection."""
from p1.core.chroma_db import chroma_db


class ChunkRepository:
    def __init__(self, chroma_db):
        # debug: chroma_db is the ChromaDB object (p1/core/chroma_db.py), not the collection.
        # The collection appears later, in get_collection().
        self.chroma_db = chroma_db

    def count(self):
        # debug: return is an int, how many Chunks are in the whole collection. No lists.
        return self.chroma_db.get_collection().count()

    def metadata_by_id(self, path):
        """{id: metadata} of every Chunk of one file."""
        # debug: path == "calculator/core.py"
        # found is Chroma columns, not objects:
        #   found["ids"] == ["aa11…", "bb22…"]  # sha256(path + "\n" + chunk text)
        #   found["metadatas"] == [
        #       {"path": "calculator/core.py", "start_line": 4, "end_line": 6,
        #        "name": "Calculator.add", "kind": "method", "hash": "…"},
        #       {"path": "calculator/core.py", "start_line": 16, "end_line": 20,
        #        "name": "Calculator.divide", "kind": "method", "hash": "…"},
        #   ]
        # return == {"aa11…": {…add…}, "bb22…": {…divide…}}
        # file not in the Index: both lists are empty, return == {}
        found = self.chroma_db.get_collection().get(where={"path": path}, include=["metadatas"])
        return dict(zip(found["ids"], found["metadatas"]))

    def all_metadata(self):
        """The metadata of every Chunk in the Index."""
        # debug: the same get, with no where. ids are dropped; only the metadatas list comes out.
        # return == [
        #     {"path": "calculator/core.py", "start_line": 1, "end_line": 20,
        #      "name": "Calculator", "kind": "class", "hash": "…"},
        #     {"path": "calculator/core.py", "start_line": 4, "end_line": 6,
        #      "name": "Calculator.add", "kind": "method", "hash": "…"},
        #     … the other Chunks of every file …
        # ]
        # empty Index: return == []
        return self.chroma_db.get_collection().get(include=["metadatas"])["metadatas"]

    def add(self, ids, texts, metadatas):
        # debug: one call. The same index in all three lists is one Chunk. No return value.
        # ids[0] + texts[0] + metadatas[0] == Calculator.add
        # ids[1] + texts[1] + metadatas[1] == Calculator.divide
        # ids == ["aa11…", "bb22…"]
        # texts == [
        #     "    def add(self, a, b):\n        \"\"\"Return a + b.\"\"\"\n        return float(a + b)",
        #     "    def divide(self, a, b):\n        …",
        # ]
        # metadatas == [
        #     {"path": "calculator/core.py", "start_line": 4, "end_line": 6,
        #      "name": "Calculator.add", "kind": "method", "hash": "…"},
        #     {"path": "calculator/core.py", "start_line": 16, "end_line": 20,
        #      "name": "Calculator.divide", "kind": "method", "hash": "…"},
        # ]
        # the text is stored as documents=texts
        self.chroma_db.get_collection().add(ids=ids, documents=texts, metadatas=metadatas)

    def delete(self, ids):
        # debug: one call deletes every id in the list. No loop here, no return value.
        # ids == ["bb22…", "cc33…"]  # every Chunk of this file whose id is gone
        self.chroma_db.get_collection().delete(ids=ids)

    def update_metadata(self, ids, metadatas):
        # debug: same text (same id), the line numbers moved. The document is not rewritten.
        # ids == ["aa11…"]
        # metadatas == [{"path": "calculator/core.py", "start_line": 6, "end_line": 8,
        #                "name": "Calculator.add", "kind": "method", "hash": "…"}]
        self.chroma_db.get_collection().update(ids=ids, metadatas=metadatas)

    def page(self, offset, limit):
        """One page of Chunks: dicts with id, text and the metadata."""
        # debug: offset == 0, limit == 200
        # found["ids"], found["documents"], found["metadatas"] are three parallel lists of one page.
        # return == [{
        #     "id": "aa11…",
        #     "text": "    def add(self, a, b):\n        …",
        #     "path": "calculator/core.py", "start_line": 4, "end_line": 6,
        #     "name": "Calculator.add", "kind": "method", "hash": "…",
        # }]
        found = self.chroma_db.get_collection().get(offset=offset, limit=limit, include=["documents", "metadatas"])
        return [dict(meta, id=id_, text=text)
                for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]


chunk_repository = ChunkRepository(chroma_db)
