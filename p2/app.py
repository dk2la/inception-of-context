"""FastAPI routes and the dashboard for Part 2."""
import contextlib
import threading

from fastapi import FastAPI

from p1 import index

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
    return {"status": "ok"}
