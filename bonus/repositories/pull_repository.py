"""Bonus pull requests, saved to a JSON file next to the Index, so the history survives a restart."""
import base64
import json
import os
import time

from p1.config.settings import settings


class PullRepository:
    def __init__(self, settings):
        self.settings = settings
        self.pulls = {}
        self.next_number = 1
        self.loaded_from = None

    def path(self):
        return os.path.join(self.settings.CHROMA_DIR, "bonus_pulls.json")

    def load(self):
        """Read the saved pull requests once per file. A missing or broken file means no history."""
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
        self.load()
        pull["number"] = self.next_number
        pull["created"] = time.time()
        self.pulls[pull["number"]] = pull
        self.next_number += 1
        self.save()
        return pull

    def get(self, number):
        self.load()
        return self.pulls.get(number)

    def all(self):
        """Every pull request, newest first."""
        self.load()
        return sorted(self.pulls.values(), key=lambda pull: pull["number"], reverse=True)


pull_repository = PullRepository(settings)
