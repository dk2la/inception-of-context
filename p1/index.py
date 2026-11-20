"""Part 1, the console command: index the Target Project once, and with --watch keep it in sync.

    python -m p1.index [dir] [--watch]

The work itself is done by p1/services/indexer.py and p1/services/watcher.py.
"""
import argparse
import os
import time

from p1.config import settings
from p1.repositories import event_repository, file_repository
from p1.services import indexer, watcher


def main():
    parser = argparse.ArgumentParser(description="Index the Target Project once.")
    parser.add_argument("dir", nargs="?", help="the folder to index (default: TARGET_DIR)")
    parser.add_argument("--watch", action="store_true", help="keep running and reindex files as they change")
    args = parser.parse_args()
    if args.dir:
        settings.TARGET_DIR = os.path.realpath(args.dir)
    chunks = indexer.index_all()
    print(f"indexed {chunks} chunks from {len(file_repository.list_files(settings.TARGET_DIR))} files")
    if args.watch:
        observer = watcher.watch()
        printed = 0  # how many events were shown already
        try:
            while True:
                for event in event_repository.events_since(printed):
                    print(f'{event["type"]} {event["path"]} ({event["chunks"]} chunks)')
                    printed += 1
                time.sleep(0.5)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
