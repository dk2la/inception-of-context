"""FastAPI routes and the dashboard for Part 2."""
import contextlib
import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from p1 import index
from p2 import ask, search

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
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

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


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


@app.get("/chunks")
def chunks(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """One page of the Chunks stored in the Index."""
    collection = index.get_collection()
    found = collection.get(offset=offset, limit=limit, include=["documents", "metadatas"])
    items = []
    for i in range(len(found["ids"])):  # ids, documents and metadatas are parallel lists
        meta = found["metadatas"][i]
        items.append({
            "id": found["ids"][i],
            "path": meta["path"],
            "start_line": meta["start_line"],
            "end_line": meta["end_line"],
            "name": meta["name"],
            "kind": meta["kind"],
            "text": found["documents"][i],
        })
    return {"total": collection.count(), "offset": offset, "limit": limit, "items": items}


def format_event(event):
    """One Server-Sent Events message: a "data:" line and an empty line."""
    return "data: " + json.dumps(event) + "\n\n"


def event_stream():
    """Send the Watcher events: first those so far, then each new one, checking twice a second."""
    sent = 0  # how many events this connection has received
    while True:
        while sent < len(index.EVENTS):
            yield format_event(index.EVENTS[sent])
            sent += 1
        # A comment line: the browser ignores it, but yielding lets the server notice a closed connection.
        # Without it this loop would never return and would keep a server thread busy after the browser left.
        yield ": waiting\n\n"
        time.sleep(0.5)


@app.get("/events")
def events():
    return StreamingResponse(event_stream(), media_type="text/event-stream")


class ContextRequest(BaseModel):
    query: str
    k: int = 5


@app.post("/context")
def context(req: ContextRequest):
    return {"results": search.search(req.query, req.k)}


class AskRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/ask")
def ask_route(req: AskRequest):
    return ask.ask(req.question, req.k)


@app.exception_handler(ask.LLMError)
def model_unreachable(request, error):
    """Any route that needs the model answers 503 with a readable message, not a generic 500."""
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/")
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
