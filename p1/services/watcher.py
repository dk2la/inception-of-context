"""The Watcher: reindex every file of the Target Project as soon as it changes."""
import os

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from p1.config.settings import settings
from p1.repositories.event_repository import event_repository
from p1.repositories.file_repository import file_repository
from p1.services.indexer import indexer_service


class WatcherService(FileSystemEventHandler):
    """The Observer calls on_any_event for every change inside the Target Project."""

    def __init__(self, settings, event_repository, file_repository, indexer_service):
        # debug: the four collaborators. watchdog will call on_any_event on this object.
        super().__init__()
        self.settings = settings
        self.event_repository = event_repository
        self.file_repository = file_repository
        self.indexer_service = indexer_service

    def on_any_event(self, event):
        # debug: saving calculator/core.py
        # event.event_type == "modified"   # also "created", "deleted", "moved"
        # event.src_path == "/workspace/calculator/core.py"
        # event.is_directory == False
        # "opened" (Linux reports it on every read) and directories return immediately
        # a move also reindexes event.dest_path: the old path is deleted, the new one is indexed
        # ".git/...", "core.py.ioc.tmp" are skipped. One failing file is printed and does not stop the loop.
        # reindex_file returns how many Chunks the file has now, e.g. 5
        # then add_event("indexed", "calculator/core.py", 5)
        # file gone from disk: add_event("deleted", "calculator/old.py", 0)
        # Reading a file makes Linux report "opened" events too; reacting to them would loop forever.
        if event.is_directory or event.event_type not in ("created", "modified", "deleted", "moved"):
            return
        paths = [event.src_path]
        if event.event_type == "moved":  # a move is a delete of the old path plus a create of the new one
            paths.append(event.dest_path)
        for path in paths:
            rel_path = self.file_repository.relative_path(path)
            if self.file_repository.is_skipped(rel_path):
                continue
            try:  # one broken file must never stop the Watcher
                chunks = self.indexer_service.reindex_file(path)
                self.event_repository.add_event("indexed" if os.path.exists(path) else "deleted", rel_path, chunks)
            except Exception as error:
                print(f"watcher: could not handle {rel_path}: {error}")

    def watch(self):
        """Start reindexing files as they change, in a background thread. Return the observer (stop it with .stop())."""
        # debug: called after index_all, from p2/app.py and from "python -m p1.index --watch".
        # WATCH_POLLING unset: observer is Observer (OS notifications), print "watching /workspace (notifications)"
        # WATCH_POLLING=1: observer is PollingObserver, print "watching /workspace (polling)"
        # schedule watches TARGET_DIR recursively. start() runs the loop on a background thread.
        # return is the observer. Stop it later with observer.stop().
        polling = self.settings.watch_polling()
        observer = PollingObserver() if polling else Observer()
        print(f"watching {self.settings.TARGET_DIR} ({'polling' if polling else 'notifications'})")
        observer.schedule(self, self.settings.TARGET_DIR, recursive=True)
        observer.start()
        return observer


watcher_service = WatcherService(settings, event_repository, file_repository, indexer_service)
