"""The Index: Chunks of the Target Project stored in ChromaDB, kept in sync with the disk."""
import argparse
import hashlib
import os
import threading
import time

import chromadb
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from p1.chunker import chunk_file, is_skipped, read_text

TARGET_DIR = os.environ.get("TARGET_DIR", "/workspace")
CHROMA_DIR = os.environ.get("CHROMA_DIR", "/data/chroma")

_collection = None
_collection_lock = threading.Lock()  # the startup thread and the first request may both open the Index
INDEX_VERSION = 0  # goes up every time the Index changes, so the keyword search knows to rebuild
EVENTS = []  # what the Watcher did, oldest first; the API streams it to the dashboard


def get_collection():
    """The one Chroma collection of this process. The Chroma client is created on first use."""
    global _collection
    with _collection_lock:
        if _collection is None:
            client = chromadb.PersistentClient(path=CHROMA_DIR)
            _collection = client.get_or_create_collection("chunks", metadata={"hnsw:space": "cosine"})
        return _collection


def chunk_id(path, text):
    """An id computed from the Chunk itself: the same path and text always give the same id."""
    return hashlib.sha256((path + "\n" + text).encode("utf-8")).hexdigest()


def metadata_of(chunk):
    """What the Index stores next to the text of a Chunk."""
    keys = ["path", "start_line", "end_line", "name", "kind", "hash"]
    return {key: chunk[key] for key in keys}


def relative_path(full_path):
    """A path the way the Index stores it: relative to the Target Project, with forward slashes."""
    return os.path.relpath(full_path, TARGET_DIR).replace(os.sep, "/")


def reindex_file(full_path):
    """Make the Index match one file on disk. Return how many Chunks the file has now.

    A file that is missing, skipped or binary has no Chunks, so its old Chunks are deleted.
    """
    global INDEX_VERSION
    rel_path = relative_path(full_path)
    if rel_path.startswith(".."):
        return 0  # outside the Target Project

    chunks = []
    text = None if is_skipped(rel_path) else read_text(full_path)
    if text is not None:
        chunks = chunk_file(rel_path, text)
    new = {chunk_id(rel_path, chunk["text"]): chunk for chunk in chunks}

    collection = get_collection()
    found = collection.get(where={"path": rel_path}, include=["metadatas"])
    old = dict(zip(found["ids"], found["metadatas"]))

    to_delete = [i for i in old if i not in new]
    to_add = [i for i in new if i not in old]
    # Same text, but the lines moved (something above it changed): update the numbers only.
    moved = [i for i in new if i in old and old[i] != metadata_of(new[i])]
    if to_delete:
        collection.delete(ids=to_delete)
    if to_add:
        collection.add(
            ids=to_add,
            documents=[new[i]["text"] for i in to_add],
            metadatas=[metadata_of(new[i]) for i in to_add],
        )
    if moved:
        collection.update(ids=moved, metadatas=[metadata_of(new[i]) for i in moved])
    if to_delete or to_add or moved:
        INDEX_VERSION += 1
    return len(new)


def add_event(type, path, chunks):
    """Write down what the Watcher did: type is "indexed" or "deleted"."""
    if type not in ("indexed", "deleted"):
        raise ValueError(f"unknown event type: {type}")
    EVENTS.append({"time": time.time(), "type": type, "path": path, "chunks": chunks})


def list_files(root):
    """Sorted absolute paths of every file under root that we should index."""
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not is_skipped(d)]  # do not even walk into skipped folders
        for name in names:
            full_path = os.path.join(folder, name)
            if not is_skipped(os.path.relpath(full_path, root)):
                found.append(os.path.abspath(full_path))
    return sorted(found)


def index_all():
    """Make the Index match the whole Target Project. Return the number of Chunks in the Index."""
    on_disk = set()
    for full_path in list_files(TARGET_DIR):
        reindex_file(full_path)
        on_disk.add(relative_path(full_path))

    # Files deleted while nobody was watching are only in the Index: reindexing them removes them.
    stored = get_collection().get(include=["metadatas"])
    for rel_path in {m["path"] for m in stored["metadatas"]} - on_disk:
        reindex_file(os.path.join(TARGET_DIR, rel_path))
    return get_collection().count()


class Handler(FileSystemEventHandler):
    """The Observer calls this for every change inside the Target Project."""

    def on_any_event(self, event):
        # Reading a file makes Linux report "opened" events too; reacting to them would loop forever.
        if event.is_directory or event.event_type not in ("created", "modified", "deleted", "moved"):
            return
        paths = [event.src_path]
        if event.event_type == "moved":  # a move is a delete of the old path plus a create of the new one
            paths.append(event.dest_path)
        for path in paths:
            rel_path = relative_path(path)
            if is_skipped(rel_path):
                continue
            try:  # one broken file must never stop the Watcher
                chunks = reindex_file(path)
                add_event("indexed" if os.path.exists(path) else "deleted", rel_path, chunks)
            except Exception as error:
                print(f"watcher: could not handle {rel_path}: {error}")


def watch():
    """Start reindexing files as they change, in a background thread. Return the observer (stop it with .stop())."""
    # Docker bind mounts on macOS and Windows often drop file notifications, so WATCH_POLLING=1 checks the files instead.
    polling = os.environ.get("WATCH_POLLING") == "1"
    observer = PollingObserver() if polling else Observer()
    print(f"watching {TARGET_DIR} ({'polling' if polling else 'notifications'})")
    observer.schedule(Handler(), TARGET_DIR, recursive=True)
    observer.start()
    return observer


def main():
    """Console command: python -m p1.index [dir] [--watch]"""
    global TARGET_DIR
    parser = argparse.ArgumentParser(description="Index the Target Project once.")
    parser.add_argument("dir", nargs="?", help="the folder to index (default: TARGET_DIR)")
    parser.add_argument("--watch", action="store_true", help="keep running and reindex files as they change")
    args = parser.parse_args()
    if args.dir:
        TARGET_DIR = os.path.realpath(args.dir)
    chunks = index_all()
    print(f"indexed {chunks} chunks from {len(list_files(TARGET_DIR))} files")
    if args.watch:
        observer = watch()
        printed = 0  # how many events were shown already
        try:
            while True:
                while printed < len(EVENTS):
                    event = EVENTS[printed]
                    print(f'{event["type"]} {event["path"]} ({event["chunks"]} chunks)')
                    printed += 1
                time.sleep(0.5)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
