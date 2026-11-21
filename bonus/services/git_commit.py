"""Commit a validated Patch. The message is one line from the local model, based on the summary."""
import os
import subprocess

from p1.config.settings import settings
from p1.core.llm import llm_client
from p1.repositories.file_repository import file_repository


class GitCommitService:
    def __init__(self, settings, llm_client, file_repository):
        # debug: settings.TARGET_DIR == "/workspace", settings.PATCH_MODEL == "qwen2.5-coder:3b"
        # commit_message asks that model for one line. commit_patch runs git only after a green Patch.
        self.settings = settings
        self.llm_client = llm_client
        self.file_repository = file_repository

    def run_git(self, root, args):
        """One git command in root. Return the completed process."""
        # debug: root == "/workspace", args == ["rev-parse", "--show-toplevel"]
        # return.returncode == 0 and return.stdout is the git root, when /workspace is inside a repo.
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)

    def repository_root(self):
        """The git root that contains the Target Project, or None when it is not in a repository."""
        # debug: /workspace inside a repo -> return == "/workspace" (the toplevel git prints)
        # /workspace with no .git -> return == None, and commit_patch refuses
        found = self.run_git(self.settings.TARGET_DIR, ["rev-parse", "--show-toplevel"])
        if found.returncode != 0:
            return None
        return found.stdout.strip()

    def commit_message(self, summary):
        """One imperative line. The summary itself is used when the model returns nothing."""
        # debug: summary == "add a power function to Calculator"
        # model text "Add a power method to Calculator\nextra" -> return == "Add a power method to Calculator"
        # empty model text -> return == "add a power function to Calculator"
        # summary "" and empty model text -> return == "apply validated patch"
        # the line is cut at 72 characters
        prompt = ("Write a single git commit message, one line, imperative mood, no quotes, "
                  "for this patch summary:\n" + summary)
        text = self.llm_client.call_llm(self.settings.PATCH_MODEL, prompt).strip()
        line = text.splitlines()[0].strip().strip('"') if text else ""
        return line[:72] or summary[:72] or "apply validated patch"

    def paths_in_repository(self, root, patch):
        """Patch paths relative to the git root. None if one of them escapes the repository."""
        # debug: root == "/workspace", files calculator/core.py and tests/test_power.py
        # return == ["calculator/core.py", "tests/test_power.py"]
        # a path that realpath sends above root -> return == None
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
        # debug: patch["summary"] == "add a power function to Calculator"
        # files calculator/core.py and tests/test_power.py are already written
        # success: return == {"ok": True, "message": "Add a power method to Calculator", "error": None}
        # no repo: return == {"ok": False, "message": None,
        #                     "error": "the Target Project is not inside a git repository"}
        # git add or git commit fails: return["ok"] == False and error is the git stderr
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
