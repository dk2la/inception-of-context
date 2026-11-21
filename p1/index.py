"""Part 1, the console command: index the Target Project once, and with --watch keep it in sync.

    python -m p1.index [dir] [--watch]

The work itself is done by p1/services/indexer.py and p1/services/watcher.py.
"""
import argparse
import os
import time

from p1.config.settings import settings
from p1.repositories.event_repository import event_repository
from p1.repositories.file_repository import file_repository
from p1.services.indexer import indexer_service
from p1.services.watcher import watcher_service


class IndexCommand:
    def __init__(self, settings, event_repository, file_repository, indexer_service, watcher_service):
        self.settings = settings
        self.event_repository = event_repository
        self.file_repository = file_repository
        self.indexer_service = indexer_service
        self.watcher_service = watcher_service

    def main(self):
        parser = argparse.ArgumentParser(description="Index the Target Project once.")
        parser.add_argument("dir", nargs="?", help="the folder to index (default: TARGET_DIR)")
        parser.add_argument("--watch", action="store_true", help="keep running and reindex files as they change")
        args = parser.parse_args()
        if args.dir:
            self.settings.TARGET_DIR = os.path.realpath(args.dir)
        chunks = self.indexer_service.index_all()
        files = len(self.file_repository.list_files(self.settings.TARGET_DIR))
        print(f"indexed {chunks} chunks from {files} files")
        if args.watch:
            observer = self.watcher_service.watch()
            printed = 0  # how many events were shown already
            try:
                while True:
                    for event in self.event_repository.events_since(printed):
                        print(f'{event["type"]} {event["path"]} ({event["chunks"]} chunks)')
                        printed += 1
                    time.sleep(0.5)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()


index_command = IndexCommand(settings, event_repository, file_repository, indexer_service, watcher_service)

if __name__ == "__main__":
    index_command.main()
