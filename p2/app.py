"""FastAPI routes and the dashboard for Part 2."""
import contextlib
import os
import threading

from fastapi import FastAPI, HTTPException

from p1 import index
from p2 import ask

WATCHER = {}  # holds the running observer, so the shutdown code can stop it


def start_indexing():
    """Catch up with the Target Project, then start the Watcher. Runs in a background thread."""
    try:
        print(f"indexing {index.TARGET_DIR} ...")
        print(f"indexed {index.index_all()} chunks")
        WATCHER["observer"] = index.watch()
    except Exception as error:
        print(f"indexing failed: {error}")


@contextlib.asynccontextmanager
async def lifespan(app):
    threading.Thread(target=start_indexing, daemon=True).start()  # a thread, so requests are answered meanwhile
    yield
    observer = WATCHER.pop("observer", None)
    if observer:
        observer.stop()
        observer.join()


app = FastAPI(lifespan=lifespan)


@app.get("/status")
def status():
    return {
        "chunks": index.get_collection().count(),
        "target_dir": index.TARGET_DIR,
        "chroma_dir": index.CHROMA_DIR,
        "answer_model": ask.ANSWER_MODEL,
        "patch_model": ask.PATCH_MODEL,
        "ollama_host": ask.OLLAMA_HOST,
    }


@app.get("/files")
def files():
    """Every file in the Index with its number of Chunks (counted from the Index, not from the disk)."""
    counts = {}
    for meta in index.get_collection().get(include=["metadatas"])["metadatas"]:
        counts[meta["path"]] = counts.get(meta["path"], 0) + 1
    return [{"path": path, "chunks": counts[path]} for path in sorted(counts)]


@app.get("/file")
def get_file(path: str):
    """One file of the Target Project: its content and the Chunk boundaries stored in the Index."""
    root = os.path.realpath(index.TARGET_DIR)
    full = os.path.realpath(os.path.join(root, path))  # realpath resolves ".." and symlinks
    rel_path = os.path.relpath(full, root).replace(os.sep, "/")
    # Never trust a path from a request: only files inside the Target Project, and only ones we index.
    if not full.startswith(root + os.sep) or index.is_skipped(rel_path):
        raise HTTPException(status_code=404, detail="file not found")
    content = index.read_text(full)
    if content is None:  # missing, a folder or binary
        raise HTTPException(status_code=404, detail="file not found")
    found = index.get_collection().get(where={"path": rel_path}, include=["metadatas"])
    chunks = [{key: meta[key] for key in ["start_line", "end_line", "name", "kind"]} for meta in found["metadatas"]]
    chunks.sort(key=lambda chunk: chunk["start_line"])
    return {"path": rel_path, "content": content, "chunks": chunks}
