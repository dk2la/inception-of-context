"""Bonus pull requests, saved to a JSON file next to the Index, so the history survives a restart."""
import base64
import json
import os
import time

from p1.config.settings import settings


class PullRepository:
    def __init__(self, settings):
        # debug: pulls starts {} and next_number starts 1, so the first pull request is #1.
        # The file is <CHROMA_DIR>/bonus_pulls.json: the Index volume, outside the Target Project (the Watcher
        # never sees it). It is read on the first use, not at import, so tests can point CHROMA_DIR elsewhere.
        self.settings = settings
        self.pulls = {}
        self.next_number = 1
        self.loaded_from = None

    def path(self):
        return os.path.join(self.settings.CHROMA_DIR, "bonus_pulls.json")

    def load(self):
        """Read the saved pull requests once per file. A missing or broken file means no history."""
        # debug: the file holds [{"number": 1, "state": "merged", "base": {"calculator/core.py": "Y2xh..."}, ...}]
        # base bytes are base64 in the file and bytes here (None stays None: the file did not exist).
        if self.loaded_from == self.path():
            return
        self.loaded_from = self.path()
        self.pulls, self.next_number = {}, 1
        try:
            with open(self.path(), encoding="utf-8") as handle:
                saved = json.load(handle)
        except (OSError, ValueError):
            return
        for pull in saved:
            pull["base"] = {path: None if data is None else base64.b64decode(data)
                            for path, data in pull.get("base", {}).items()}
            self.pulls[pull["number"]] = pull
        self.next_number = max(self.pulls, default=0) + 1

    def save(self):
        """Write every pull request. Called after each change; a failed write only loses the history."""
        saved = []
        for pull in self.pulls.values():
            copy = dict(pull)
            copy["base"] = {path: None if data is None else base64.b64encode(data).decode()
                            for path, data in pull.get("base", {}).items()}
            saved.append(copy)
        try:
            os.makedirs(os.path.dirname(self.path()), exist_ok=True)
            with open(self.path(), "w", encoding="utf-8") as handle:
                json.dump(saved, handle)
        except OSError:
            pass

    def add(self, pull):
        """Store a new pull request under the next number and return it."""
        # debug: pull == {"title": "add power", "state": "open", ...} -> pull["number"] == 1, pull["created"] is now
        self.load()
        pull["number"] = self.next_number
        pull["created"] = time.time()
        self.pulls[pull["number"]] = pull
        self.next_number += 1
        self.save()
        return pull

    def get(self, number):
        # debug: get(1) -> the pull request #1. get(99) -> None
        self.load()
        return self.pulls.get(number)

    def all(self):
        """Every pull request, newest first."""
        # debug: #1 and #2 stored -> return == [pull2, pull1]
        self.load()
        return sorted(self.pulls.values(), key=lambda pull: pull["number"], reverse=True)


pull_repository = PullRepository(settings)
