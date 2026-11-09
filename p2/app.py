"""FastAPI routes and the dashboard for Part 2."""
import contextlib
import threading

from fastapi import FastAPI

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
