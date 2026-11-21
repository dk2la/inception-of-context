"""Commit a validated Patch. The message is one line from the local model, based on the summary."""
import os
import subprocess

from p1.config.settings import settings
from p1.core.llm import llm_client
from p1.repositories.file_repository import file_repository


class GitCommitService:
    def __init__(self, settings, llm_client, file_repository):
        self.settings = settings
        self.llm_client = llm_client
        self.file_repository = file_repository

    def run_git(self, root, args):
        """One git command in root. Return the completed process."""
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)

    def repository_root(self):
        """The git root that contains the Target Project, or None when it is not in a repository."""
        found = self.run_git(self.settings.TARGET_DIR, ["rev-parse", "--show-toplevel"])
        if found.returncode != 0:
            return None
        return found.stdout.strip()

    def commit_message(self, summary):
        """One imperative line. The summary itself is used when the model returns nothing."""
        prompt = ("Write a single git commit message, one line, imperative mood, no quotes, "
                  "for this patch summary:\n" + summary)
        text = self.llm_client.call_llm(self.settings.PATCH_MODEL, prompt).strip()
        line = text.splitlines()[0].strip().strip('"') if text else ""
        return line[:72] or summary[:72] or "apply validated patch"

    def paths_in_repository(self, root, patch):
        """Patch paths relative to the git root. None if one of them escapes the repository."""
        relative = []
        for entry in patch["files"]:
            full = os.path.realpath(self.file_repository.full_path(entry["path"]))
            rel = os.path.relpath(full, root)
            if rel.startswith(".."):
                return None
            relative.append(rel)
        return relative

    def commit_patch(self, patch):
        """Commit just the files of a validated Patch. The Patch itself is already on disk."""
        root = self.repository_root()
        if root is None:
            return {"ok": False, "message": None, "error": "the Target Project is not inside a git repository"}
        paths = self.paths_in_repository(root, patch)
        if not paths:
            return {"ok": False, "message": None, "error": "the Patch files are outside the git repository"}
        message = self.commit_message(patch.get("summary") or "")
        added = self.run_git(root, ["add", "-A", "--", *paths])
        if added.returncode != 0:
            return {"ok": False, "message": message, "error": added.stderr.strip() or "git add failed"}
        committed = self.run_git(root, ["commit", "-m", message, "--", *paths])
        if committed.returncode != 0:
            return {"ok": False, "message": message, "error": committed.stderr.strip() or committed.stdout.strip()}
        return {"ok": True, "message": message, "error": None}


git_commit_service = GitCommitService(settings, llm_client, file_repository)
