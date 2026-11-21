"""Part 2: the API and the dashboard. This file only puts the layers together:
the routes of Part 1 (status, files, Chunks, events) and of Part 2 (questions, dashboard).

    uvicorn p2.app:app     (without /patch: the Patch Loop tab says "not available")
"""
import contextlib
import threading

from fastapi import FastAPI

from p1.config.settings import settings
from p1.services.indexer import indexer_service
from p1.services.watcher import watcher_service
from p1.views.events import events_view
from p1.views.overview import overview_view
from p2.views.dashboard import dashboard_view
from p2.views.errors import error_handlers
from p2.views.llm_live import llm_live_view
from p2.views.questions import questions_view


class Lifecycle:
    """Indexing at startup and the Watcher, which runs until the server stops."""

    def __init__(self, settings, indexer_service, watcher_service):
        self.settings = settings
        self.indexer_service = indexer_service
        self.watcher_service = watcher_service
        self.observer = None  # the running Watcher, so the shutdown code can stop it

    def start_indexing(self):
        """Catch up with the Target Project, then start the Watcher. Runs in a background thread."""
        try:
            print(f"indexing {self.settings.TARGET_DIR} ...")
            print(f"indexed {self.indexer_service.index_all()} chunks")
            self.observer = self.watcher_service.watch()
        except Exception as error:
            print(f"indexing failed: {error}")

    @contextlib.asynccontextmanager
    async def lifespan(self, app):
        # A thread, so requests are answered while the first index is still running.
        threading.Thread(target=self.start_indexing, daemon=True).start()
        yield
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None


lifecycle = Lifecycle(settings, indexer_service, watcher_service)

app = FastAPI(title="Inception-of-Context", lifespan=lifecycle.lifespan)
for view in (overview_view, events_view, questions_view, llm_live_view, dashboard_view):
    app.include_router(view.router)
error_handlers.add_error_handlers(app)
