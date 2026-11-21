"""The bonus pull request: a Patch whose checks passed, held until someone merges or closes it."""
import time

from p3.models.patch import attempt_factory
from p3.repositories.target_files import target_files_repository
from p3.services.patch_loop import patch_loop_service
from bonus.repositories.event_repository import bonus_event_repository
from bonus.repositories.pull_repository import pull_repository
from bonus.services.git_commit import git_commit_service


class PullRequestService:
    def __init__(self, pulls, patch_loop_service, target_files_repository, attempt_factory, git_commit_service, events):
        # debug: pulls is the in-memory pull_repository. Merge holds the same patch_lock as the Patch Loop.
        self.pulls = pulls
        self.patch_loop_service = patch_loop_service
        self.target_files_repository = target_files_repository
        self.attempt_factory = attempt_factory
        self.git_commit_service = git_commit_service
        self.events = events

    def view(self, pull):
        """The pull request as JSON. base (the bytes the Patch was checked against) stays on the server."""
        # debug: return has number, title, intent, state, files, checks, attempts, created, merge. No "base".
        return {key: value for key, value in pull.items() if key != "base"}

    def open(self, intent, patch, attempts, diffs):
        """Open a pull request for a Patch that passed the Sanity Checks and the Validation Command."""
        # debug: intent == "add a power function to Calculator", attempts[-1]["ok"] is True, the disk is restored.
        # return["number"] == 1, return["state"] == "open", return["title"] == patch["summary"]
        # checks == {"sanity": True, "validation": True, "log": "3 passed"}
        # base is the current bytes of every file the Patch touches; Merge refuses when they changed.
        last = attempts[-1]
        pull = self.pulls.add({
            "title": patch["summary"] or intent,
            "intent": intent,
            "state": "open",
            "patch": patch,
            "files": diffs,
            "checks": {"sanity": True, "validation": True,
                       "log": self.patch_loop_service.last_lines(last["validation"]["log"], 20)},
            "attempts": len(attempts),
            "merge": None,
            "base": self.target_files_repository.take_snapshot([f["path"] for f in patch["files"]]),
        })
        self.events.add("pull_opened", {"number": pull["number"], "title": pull["title"]})
        return self.view(pull)

    def list(self):
        # debug: GET /bonus/pulls -> [#2 view, #1 view]
        return [self.view(pull) for pull in self.pulls.all()]

    def reply(self, status, pull, attempts, git, error=None):
        # debug: the same keys as a bonus patch reply, so the dashboard draws a Merge like a run.
        return {"status": status, "attempts": attempts, "patch": pull["patch"], "diffs": pull["files"],
                "git": git, "dry_run": False, "error": error, "pull": self.view(pull)}

    def merge(self, number, git_commit=True):
        """Apply exactly the stored Patch, validate it again, then optionally commit. None for an unknown number."""
        # debug: POST /bonus/pulls/1/merge {"git_commit": true}
        # green: status == "success", state == "merged", the Patch stays on disk, git is the commit result
        # a file changed since the pull request was opened: status == "conflict", nothing written, still open
        # validation red at merge: status == "failed", the files are rolled back, the pull request stays open
        # already merged or closed: status == "refused"
        with self.patch_loop_service.patch_lock:
            pull = self.pulls.get(number)
            if pull is None:
                return None
            if pull["state"] != "open":
                return self.reply("refused", pull, [], None, f"pull request #{number} is {pull['state']}")
            paths = [f["path"] for f in pull["patch"]["files"]]
            current = self.target_files_repository.take_snapshot(paths)
            changed = [path for path in paths if current[path] != pull["base"][path]]
            if changed:
                error = "changed since the pull request was opened: " + ", ".join(changed)
                self.events.add("pull_conflict", {"number": number, "files": changed})
                return self.reply("conflict", pull, [], None, error)
            self.events.add("attempt_started", {"number": 1, "step": "merge"})
            attempt = self.attempt_factory.new_attempt(1)
            attempt["generation"] = {"ok": True, "summary": pull["patch"]["summary"]}
            attempt = self.patch_loop_service.try_patch(attempt, pull["patch"])
            if not attempt["ok"]:
                self.events.add("pull_failed", {"number": number, "error": attempt["error"]})
                return self.reply("failed", pull, [attempt], None, attempt["error"])
            git = None
            if git_commit:
                git = self.git_commit_service.commit_patch(pull["patch"])
                self.events.add("git", git)
            pull["state"] = "merged"
            pull["merge"] = {"git": git, "at": time.time()}
            self.pulls.save()
            self.events.add("pull_merged", {"number": number, "title": pull["title"]})
            return self.reply("success", pull, [attempt], git)

    def close(self, number):
        """Close an open pull request without touching the disk. None for an unknown number."""
        # debug: POST /bonus/pulls/1/close -> return["state"] == "closed". Closing it again changes nothing.
        pull = self.pulls.get(number)
        if pull is None:
            return None
        if pull["state"] == "open":
            pull["state"] = "closed"
            pull["closed_at"] = time.time()
            self.pulls.save()
            self.events.add("pull_closed", {"number": number, "title": pull["title"]})
        return self.view(pull)


pull_request_service = PullRequestService(pull_repository, patch_loop_service, target_files_repository,
                                          attempt_factory, git_commit_service, bonus_event_repository)
