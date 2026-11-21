"""Bonus pull requests, kept in memory. A restart forgets them, like the live events."""
import time


class PullRepository:
    def __init__(self):
        # debug: pulls starts {} and next_number starts 1, so the first pull request is #1.
        self.pulls = {}
        self.next_number = 1

    def add(self, pull):
        """Store a new pull request under the next number and return it."""
        # debug: pull == {"title": "add power", "state": "open", ...} -> pull["number"] == 1, pull["created"] is now
        pull["number"] = self.next_number
        pull["created"] = time.time()
        self.pulls[pull["number"]] = pull
        self.next_number += 1
        return pull

    def get(self, number):
        # debug: get(1) -> the pull request #1. get(99) -> None
        return self.pulls.get(number)

    def all(self):
        """Every pull request, newest first."""
        # debug: #1 and #2 stored -> return == [pull2, pull1]
        return sorted(self.pulls.values(), key=lambda pull: pull["number"], reverse=True)


pull_repository = PullRepository()
