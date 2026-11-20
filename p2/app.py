"""Part 2: the API and the dashboard. This file only puts the layers together:
the routes of Part 1 (status, files, Chunks, events) and of Part 2 (questions, dashboard).

    uvicorn p2.app:app     (without /patch: the Patch Loop tab says "not available")
"""
import contextlib
import threading

from fastapi import FastAPI

from p1.config import settings
from p1.services import indexer
from p1.services import watcher
from p1.views import events, overview
from p2.views import dashboard, questions
from p2.views.errors import add_error_handlers

OBSERVER = None  # the running Watcher, so the shutdown code can stop it


def start_indexing():
    """Catch up with the Target Project, then start the Watcher. Runs in a background thread."""
    global OBSERVER
    try:
        print(f"indexing {settings.TARGET_DIR} ...")
        print(f"indexed {indexer.index_all()} chunks")
        OBSERVER = watcher.watch()
    except Exception as error:
        print(f"indexing failed: {error}")


@contextlib.asynccontextmanager
async def lifespan(app):
    global OBSERVER
    threading.Thread(target=start_indexing, daemon=True).start()  # a thread, so requests are answered meanwhile
    yield
    if OBSERVER:
        OBSERVER.stop()
        OBSERVER.join()
        OBSERVER = None


app = FastAPI(title="Inception-of-Context", lifespan=lifespan)
for view in (overview, events, questions, dashboard):
    app.include_router(view.router)
add_error_handlers(app)
