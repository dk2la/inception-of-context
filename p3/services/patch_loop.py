"""The Patch Loop: Intent -> Patch -> Sanity Checks -> apply -> Validation Command -> Rollback on failure."""
import json
import threading

from p1.config.settings import settings
from p1.core.llm import llm_client
from p1.repositories.file_repository import file_repository
from p2.services.search import search_service
from p3.models.patch import OPS, attempt_factory
from p3.repositories.target_files import target_files_repository
from p3.services.sanity import MARKER, sanity_service
from p3.services.validation import validation_service


PATCH_RULES = f"""Reply with ONLY a JSON object of this shape:
{{"summary": "...", "files": [{{"path": "...", "op": "create" | "modify" | "delete", "content": "..."}}]}}
- content is the COMPLETE new file, not a diff and not only the changed function.
- Use paths exactly as listed under FILES IN THE PROJECT. Use "create" only for a new path.
- Never rewrite an existing test file. To add tests, create a NEW file such as tests/test_<feature>.py.
- Change at most {settings.MAX_FILES} files. Never change {settings.VALIDATION_CONFIG}.
- Do not put "{MARKER}" lines in content.
- Do not write placeholder functions (pass, ..., return None)."""


class PatchLoopService:
    def __init__(self, settings, llm_client, file_repository, search_service, attempt_factory,
                 target_files_repository, sanity_service, validation_service):
        self.settings = settings
        self.llm_client = llm_client
        self.file_repository = file_repository
        self.search_service = search_service
        self.attempt_factory = attempt_factory
        self.target_files_repository = target_files_repository
        self.sanity_service = sanity_service
        self.validation_service = validation_service
        self.patch_lock = threading.Lock()  # a second Patch Loop would snapshot the files the first one is changing

    def parse_patch(self, text):
        """Read the model's JSON answer. Return (patch, None), or (None, reason) if its shape is wrong."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return None, f"the model did not return valid JSON: {e}"
        if not isinstance(data, dict):
            return None, "the Patch must be a JSON object"
        if not isinstance(data.get("files"), list) or not data["files"]:
            return None, "the Patch has no files"
        summary = data["summary"] if isinstance(data.get("summary"), str) else ""
        files = []
        for number, entry in enumerate(data["files"], start=1):
            if not isinstance(entry, dict):
                return None, f"file {number}: must be a JSON object"
            path, op, content = entry.get("path"), entry.get("op"), entry.get("content")
            if not isinstance(path, str) or not path:
                return None, f"file {number}: path must be a non-empty string"
            if op not in OPS:
                return None, f"file {number}: op must be create, modify or delete, got {op!r}"
            if op == "delete":
                content = ""
            elif not isinstance(content, str):
                return None, f"file {number}: content must be a string"
            files.append({"path": path, "op": op, "content": content})
        return {"summary": summary, "files": files}, None

    def last_lines(self, text, count=40):
        """The end of a log is where the error is, so that is the part we keep."""
        return "\n".join(text.splitlines()[-count:])

    def build_patch_prompt(self, intent, k, previous=None):
        """The text for one Attempt. previous is None, or {"patch": the last Patch or None, "error": why it failed}."""
        names = [self.file_repository.relative_path(p) for p in self.file_repository.list_files(self.settings.TARGET_DIR)]
        parts = ["FILES IN THE PROJECT:\n" + "\n".join(names)]
        # The Chunks only say which files matter; the model gets each of those files whole, once.
        for path in dict.fromkeys(chunk["path"] for chunk in self.search_service.search(intent, k)):
            text = self.file_repository.read_text(self.file_repository.full_path(path))
            if text is not None:
                parts.append(f"{MARKER} {path} ===\n{text}")
        parts.append("INTENT: " + intent)
        parts.append(PATCH_RULES)
        if previous:
            patch = json.dumps(previous["patch"], indent=2) if previous["patch"] else "no valid Patch"
            error = self.last_lines(previous["error"])
            parts.append(f"YOUR PREVIOUS ATTEMPT FAILED.\nYour previous Patch:\n{patch}\nWhy it failed:\n{error}")
        return "\n\n".join(parts)

    def run_attempt(self, intent, k, previous, number):
        """One Attempt: generate, parse, Sanity Checks, snapshot, apply, validate. A failed Attempt is rolled back."""
        attempt = self.attempt_factory.new_attempt(number)
        text = self.llm_client.call_llm(self.settings.PATCH_MODEL, self.build_patch_prompt(intent, k, previous), json_mode=True)
        patch, reason = self.parse_patch(text)
        if reason:
            attempt["generation"] = {"ok": False, "error": reason}
            attempt["error"] = reason
            return attempt
        attempt["patch"] = patch
        attempt["generation"] = {"ok": True, "summary": patch["summary"]}
        reason = self.sanity_service.check_patch(patch, self.settings.TARGET_DIR)
        if reason:
            attempt["sanity"] = {"ok": False, "reason": reason}
            attempt["error"] = "sanity check refused the patch: " + reason
            return attempt
        attempt["sanity"] = {"ok": True, "reason": None}
        snapshot = self.target_files_repository.take_snapshot([f["path"] for f in patch["files"]])
        try:
            attempt["apply"] = {"ok": True, "files": self.target_files_repository.apply_patch(patch)}
            changed = [f["path"] for f in patch["files"] if f["op"] != "delete"]
            ok, log = self.validation_service.run_validation(changed)
            attempt["validation"] = {"ok": ok, "log": log}
            if ok:
                attempt["ok"] = True
                return attempt  # the Watcher reindexes the changed files
            attempt["error"] = "validation failed:\n" + self.last_lines(log)
        except Exception as e:
            if attempt["apply"] is None:
                attempt["apply"] = {"ok": False, "error": str(e)}
                attempt["error"] = "could not apply the patch: " + str(e)
            else:  # applying worked, but the Validation Command could not run
                attempt["validation"] = {"ok": False, "log": str(e)}
                attempt["error"] = "validation failed:\n" + str(e)
        self.target_files_repository.restore_snapshot(snapshot)  # whatever failed, the next Attempt starts from the original code
        return attempt

    def run_patch_loop(self, intent, k=5, max_attempts=settings.MAX_ATTEMPTS):
        """Try up to max_attempts (1 to MAX_ATTEMPTS) Attempts, telling the model why the last one failed."""
        with self.patch_lock:  # one Patch Loop at a time; another request waits here
            attempts = []
            previous = None
            for number in range(1, max(1, min(self.settings.MAX_ATTEMPTS, max_attempts)) + 1):
                attempt = self.run_attempt(intent, k, previous, number)
                attempts.append(attempt)
                if attempt["ok"]:
                    return {"status": "success", "attempts": attempts, "patch": attempt["patch"]}
                previous = {"patch": attempt["patch"], "error": attempt["error"]}
            return {"status": "failed", "attempts": attempts, "patch": None}


patch_loop_service = PatchLoopService(settings, llm_client, file_repository, search_service, attempt_factory,
                                      target_files_repository, sanity_service, validation_service)
