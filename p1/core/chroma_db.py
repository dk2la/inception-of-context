"""The Index database, ChromaDB: one Chroma collection, shared by every part of this process.

One Chroma client per process (ADR-0002): the Watcher thread and the API requests share it.
This is the only module that imports chromadb; the repositories of p1 and p2 use chroma_db.get_collection().
"""
import threading

import chromadb

from p1.config.settings import settings


class ChromaDB:
    def __init__(self, settings):
        self.settings = settings
        self._collection = None
        self._collection_lock = threading.Lock()
        self.INDEX_VERSION = 0

    def get_collection(self):
        """The one Chroma collection of this process. The Chroma client is created on first use."""
        with self._collection_lock:
            if self._collection is None:
                client = chromadb.PersistentClient(path=self.settings.CHROMA_DIR)
                self._collection = client.get_or_create_collection(
                    self.settings.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
            return self._collection

    def mark_changed(self):
        """Call after Chunks were added or deleted."""
        self.INDEX_VERSION += 1


chroma_db = ChromaDB(settings)
