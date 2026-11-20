"""The Index database: one ChromaDB collection, shared by every part of this process.

One Chroma client per process (ADR-0002): the Watcher thread and the API requests share it.
This is the only module that imports chromadb; the repositories of p1 and p2 use get_collection().
"""
import threading

import chromadb

from p1.config import settings

_collection = None
_collection_lock = threading.Lock()  # the startup thread and the first request may both open the Index
INDEX_VERSION = 0  # goes up every time Chunk texts change, so the keyword search knows to rebuild


def get_collection():
    """The one Chroma collection of this process. The Chroma client is created on first use."""
    global _collection
    with _collection_lock:
        if _collection is None:
            client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
            _collection = client.get_or_create_collection(settings.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        return _collection


def mark_changed():
    """Call after Chunks were added or deleted."""
    global INDEX_VERSION
    INDEX_VERSION += 1
