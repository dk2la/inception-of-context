"""The bonus Patch Loop: a dry-run diff, a real loop with live events, then an optional git commit."""
from p1.config.settings import settings
from p1.core.llm import llm_client
from p1.repositories.file_repository import file_repository
from p3.models.patch import attempt_factory
from p3.services.patch_loop import patch_loop_service
from p3.services.sanity import sanity_service
from bonus.repositories.event_repository import bonus_event_repository
from bonus.services.diff import diff_service
from bonus.services.git_commit import git_commit_service
from bonus.services.pull_request import pull_request_service


class PatchBonusService:
    def __init__(self, settings, llm_client, file_repository, patch_loop_service, sanity_service,
                 attempt_factory, diff_service, git_commit_service, events, pull_request_service):
        # debug: dry_run calls qwen2.5-coder:3b once. A real run calls patch_loop_service.run_attempt.
        # events is bonus_event_repository. The dashboard reads those events from GET /bonus/events.
        self.settings = settings
        self.llm_client = llm_client
        self.file_repository = file_repository
        self.patch_loop_service = patch_loop_service
        self.sanity_service = sanity_service
        self.attempt_factory = attempt_factory
        self.diff_service = diff_service
        self.git_commit_service = git_commit_service
        self.events = events
        self.pull_request_service = pull_request_service

    def read(self, path):
        """The current text of one Target Project file, or "" when it does not exist."""
        # debug: path == "calculator/core.py" -> return is the 21-line class, starting "class Calculator:"
        # path == "tests/test_power.py" before it is created -> return == ""
        text = self.file_repository.read_text(self.file_repository.full_path(path))
        return text if text is not None else ""

    def diffs_for(self, patch):
        """A unified diff per file in the Patch, against the text on disk right now."""
        # debug: used by dry_run, before any write. patch modifies calculator/core.py.
        # diffs[0] == {"path": "calculator/core.py", "op": "modify", "diff": "--- a/calculator/core.py\n..."}
        # op "delete" diffs against the current text and an empty new text.
        diffs = []
        for entry in patch["files"]:
            new = "" if entry["op"] == "delete" else entry.get("content") or ""
            diffs.append({"path": entry["path"], "op": entry["op"],
                          "diff": self.diff_service.unified(entry["path"], self.read(entry["path"]), new)})
        return diffs

    def snapshot(self):
        """Text of every indexed file, taken before a real Patch Loop overwrites them."""
        # debug: saved["calculator/core.py"] is the class text from before apply_patch.
        # a missing file is absent from saved, so a later create diffs against "".
        saved = {}
        for full in self.file_repository.list_files(self.settings.TARGET_DIR):
            rel = self.file_repository.relative_path(full)
            text = self.file_repository.read_text(full)
            if text is not None:
                saved[rel] = text
        return saved

    def diffs_from_snapshot(self, saved, patch):
        """Diffs of the files the Patch touched, using the snapshot taken before it was applied."""
        # debug: apply_patch has already replaced calculator/core.py, so the old text comes from saved.
        # saved["calculator/core.py"] is the 21-line class. new is patch content, the class plus power.
        # return[0]["diff"] starts with "--- a/calculator/core.py\n+++ b/calculator/core.py\n"
        diffs = []
        for entry in patch["files"]:
            new = "" if entry["op"] == "delete" else entry.get("content") or ""
            old = saved.get(entry["path"], "")
            diffs.append({"path": entry["path"], "op": entry["op"],
                          "diff": self.diff_service.unified(entry["path"], old, new)})
        return diffs

    def reply(self, status, attempts, patch, diffs, git, dry_run):
        # debug: a green real run returns
        # {"status": "success", "attempts": [attempt], "patch": {...}, "diffs": [...],
        #  "git": {"ok": True, "message": "Add a power method to Calculator", "error": None},
        #  "dry_run": False}
        return {"status": status, "attempts": attempts, "patch": patch,
                "diffs": diffs, "git": git, "dry_run": dry_run}

    def note_attempt(self, attempt):
        """Tell the live feed how this Attempt ended, including the validation result."""
        # debug: pytest of the calculator failed. events.add("attempt", {
        #   "number": 1, "ok": False, "validation_ok": False, "error": "validation failed:\n..."})
        # a sanity refusal has no validation key, so validation_ok is None
        validation = attempt.get("validation") or {}
        self.events.add("attempt", {
            "number": attempt["number"],
            "ok": attempt["ok"],
            "validation_ok": validation.get("ok"),
            "error": attempt.get("error"),
        })

    def dry_run(self, intent, k):
        """Generate one Patch and its diff. Sanity still runs. The disk is not touched."""
        # debug: intent == "add a power function to Calculator", k == 5. One call to qwen2.5-coder:3b.
        # valid patch that passes sanity:
        #   return status == "dry_run", diffs filled, git is None, dry_run is True. Disk unchanged.
        # "not json": status == "refused", patch is None, diffs == []
        # sanity refuses 4 files: status == "refused", patch and diffs are still returned
        self.events.add("attempt_started", {"number": 1, "step": "dry_run"})
        text = self.llm_client.call_llm(
            self.settings.PATCH_MODEL, self.patch_loop_service.build_patch_prompt(intent, k, None), json_mode=True)
        patch, reason = self.patch_loop_service.parse_patch(text)
        attempt = self.attempt_factory.new_attempt(1)
        if reason:
            attempt["generation"] = {"ok": False, "error": reason}
            attempt["error"] = reason
            self.note_attempt(attempt)
            return self.reply("refused", [attempt], None, [], None, True)
        attempt["patch"] = patch
        attempt["generation"] = {"ok": True, "summary": patch["summary"]}
        reason = self.sanity_service.check_patch(patch, self.settings.TARGET_DIR)
        diffs = self.diffs_for(patch)
        if reason:
            attempt["sanity"] = {"ok": False, "reason": reason}
            attempt["error"] = "sanity check refused the patch: " + reason
            self.note_attempt(attempt)
            return self.reply("refused", [attempt], patch, diffs, None, True)
        attempt["sanity"] = {"ok": True, "reason": None}
        self.note_attempt(attempt)
        self.events.add("dry_run", {"files": [item["path"] for item in diffs]})
        return self.reply("dry_run", [attempt], patch, diffs, None, True)

    def run(self, intent, k=5, max_attempts=3, dry_run=False, git_commit=True, pull_request=False):
        """Dry-run, or the real loop. A green Patch can be committed. Events go out as each Attempt ends."""
        # pull_request True: the same loop, but a green Patch is rolled back and opened as a pull request.
        #   status == "open", return["pull"]["number"] == 1, the disk is unchanged, git stays None.
        #   POST /bonus/pulls/1/merge then applies exactly that Patch.
        # debug: POST /bonus/patch {"intent": "add a power function to Calculator", "k": 5,
        #   "max_attempts": 3, "dry_run": false, "git_commit": true}
        # the same non-reentrant patch_lock is held here, so this method calls run_attempt, not run_patch_loop
        # dry_run True: return is dry_run(), status "dry_run" or "refused", nothing written
        # pytest green: status == "success", diffs come from the snapshot, git is the commit result
        # three failures: status == "failed", patch is None, diffs == [], git stays None
        # max_attempts 0 or 99 is clamped to 1..3
        with self.patch_loop_service.patch_lock:
            self.events.add("started", {"intent": intent, "dry_run": dry_run, "pull_request": pull_request})
            if dry_run:
                result = self.dry_run(intent, k)
                self.events.add("finished", {"status": result["status"]})
                return result
            saved = self.snapshot()
            attempts = []
            previous = None
            limit = max(1, min(self.settings.MAX_ATTEMPTS, max_attempts))
            for number in range(1, limit + 1):
                self.events.add("attempt_started", {"number": number, "step": "validation"})
                if pull_request:
                    attempt = self.patch_loop_service.run_attempt(intent, k, previous, number, keep=False)
                else:
                    attempt = self.patch_loop_service.run_attempt(intent, k, previous, number)
                attempts.append(attempt)
                self.note_attempt(attempt)
                if attempt["ok"]:
                    break
                previous = {"patch": attempt["patch"], "error": attempt["error"]}
            success = attempts[-1]["ok"]
            patch = attempts[-1]["patch"] if success else None
            diffs = self.diffs_from_snapshot(saved, patch) if patch else []
            git = None
            if success and pull_request:
                result = self.reply("open", attempts, patch, diffs, None, False)
                result["pull"] = self.pull_request_service.open(intent, patch, attempts, diffs)
                self.events.add("finished", {"status": "open"})
                return result
            if success and git_commit:
                git = self.git_commit_service.commit_patch(patch)
                self.events.add("git", git)
            status = "success" if success else "failed"
            self.events.add("finished", {"status": status})
            return self.reply(status, attempts, patch, diffs, git, False)


patch_bonus_service = PatchBonusService(
    settings, llm_client, file_repository, patch_loop_service, sanity_service,
    attempt_factory, diff_service, git_commit_service, bonus_event_repository, pull_request_service)
