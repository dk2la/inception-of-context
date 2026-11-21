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


class PatchBonusService:
    def __init__(self, settings, llm_client, file_repository, patch_loop_service, sanity_service,
                 attempt_factory, diff_service, git_commit_service, events):
        self.settings = settings
        self.llm_client = llm_client
        self.file_repository = file_repository
        self.patch_loop_service = patch_loop_service
        self.sanity_service = sanity_service
        self.attempt_factory = attempt_factory
        self.diff_service = diff_service
        self.git_commit_service = git_commit_service
        self.events = events

    def read(self, path):
        """The current text of one Target Project file, or "" when it does not exist."""
        text = self.file_repository.read_text(self.file_repository.full_path(path))
        return text if text is not None else ""

    def diffs_for(self, patch):
        """A unified diff per file in the Patch, against the text on disk right now."""
        diffs = []
        for entry in patch["files"]:
            new = "" if entry["op"] == "delete" else entry.get("content") or ""
            diffs.append({"path": entry["path"], "op": entry["op"],
                          "diff": self.diff_service.unified(entry["path"], self.read(entry["path"]), new)})
        return diffs

    def snapshot(self):
        """Text of every indexed file, taken before a real Patch Loop overwrites them."""
        saved = {}
        for full in self.file_repository.list_files(self.settings.TARGET_DIR):
            rel = self.file_repository.relative_path(full)
            text = self.file_repository.read_text(full)
            if text is not None:
                saved[rel] = text
        return saved

    def diffs_from_snapshot(self, saved, patch):
        """Diffs of the files the Patch touched, using the snapshot taken before it was applied."""
        diffs = []
        for entry in patch["files"]:
            new = "" if entry["op"] == "delete" else entry.get("content") or ""
            old = saved.get(entry["path"], "")
            diffs.append({"path": entry["path"], "op": entry["op"],
                          "diff": self.diff_service.unified(entry["path"], old, new)})
        return diffs

    def reply(self, status, attempts, patch, diffs, git, dry_run):
        return {"status": status, "attempts": attempts, "patch": patch,
                "diffs": diffs, "git": git, "dry_run": dry_run}

    def note_attempt(self, attempt):
        """Tell the live feed how this Attempt ended, including the validation result."""
        validation = attempt.get("validation") or {}
        self.events.add("attempt", {
            "number": attempt["number"],
            "ok": attempt["ok"],
            "validation_ok": validation.get("ok"),
            "error": attempt.get("error"),
        })

    def dry_run(self, intent, k):
        """Generate one Patch and its diff. Sanity still runs. The disk is not touched."""
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

    def run(self, intent, k=5, max_attempts=3, dry_run=False, git_commit=True):
        """Dry-run, or the real loop. A green Patch can be committed. Events go out as each Attempt ends."""
        with self.patch_loop_service.patch_lock:
            self.events.add("started", {"intent": intent, "dry_run": dry_run})
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
            if success and git_commit:
                git = self.git_commit_service.commit_patch(patch)
                self.events.add("git", git)
            status = "success" if success else "failed"
            self.events.add("finished", {"status": status})
            return self.reply(status, attempts, patch, diffs, git, False)


patch_bonus_service = PatchBonusService(
    settings, llm_client, file_repository, patch_loop_service, sanity_service,
    attempt_factory, diff_service, git_commit_service, bonus_event_repository)
