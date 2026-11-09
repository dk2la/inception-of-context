"""The Patch Loop: the small steps it is built from (config, validate, snapshot, apply, parse)."""
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile

import yaml

from p1 import index
from p1.chunker import read_text
from p2 import search
from p3.sanity import MARKER, MAX_FILES

VALIDATION_TIMEOUT = 60  # seconds


def load_validation_command():
    """The Validation Command from the Target Project's ioc.config.yml."""
    with open(os.path.join(index.TARGET_DIR, "ioc.config.yml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    command = config.get("validate") if isinstance(config, dict) else None
    if not isinstance(command, str) or not command:
        raise ValueError("ioc.config.yml must contain a 'validate' command")
    return command


def full_path(rel_path):
    """The real path of a Patch path, which is relative to the Target Project."""
    return os.path.join(index.TARGET_DIR, rel_path)


def run_validation(changed_files):
    """Run the Validation Command. Return (ok, log)."""
    py_files = [p for p in changed_files if p.endswith(".py") and os.path.isfile(full_path(p))]
    # "-" makes py_compile read file names from the (empty) stdin, so it compiles nothing and succeeds
    files_text = " ".join(shlex.quote(p) for p in py_files) or "-"
    command = load_validation_command().replace("{files}", files_text)
    # "python" in the command must be the interpreter that runs this server, even if it is not on PATH
    path = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
    # Python skips recompiling a file whose size and modification second match its old .pyc. After a Rollback
    # that can run the patched code, so validation keeps its .pyc files in a temporary folder, not in the project.
    with tempfile.TemporaryDirectory() as pycache:
        # Popen, not run: with shell=True, run() on timeout kills only the shell, and pytest keeps running.
        # start_new_session puts the shell and its children in one process group that we can kill together.
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=index.TARGET_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=dict(os.environ, PATH=path, PYTHONPYCACHEPREFIX=pycache),
            start_new_session=True,
        )
        try:
            log, _ = proc.communicate(timeout=VALIDATION_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return False, f"validation timed out after {VALIDATION_TIMEOUT} seconds"
    return proc.returncode == 0, log


def take_snapshot(paths):
    """Remember the exact bytes of each file before a Patch touches it (None if the file does not exist)."""
    snapshot = {}
    for rel_path in paths:
        if os.path.isfile(full_path(rel_path)):
            with open(full_path(rel_path), "rb") as f:
                snapshot[rel_path] = f.read()
        else:
            snapshot[rel_path] = None
    return snapshot


def restore_snapshot(snapshot):
    """Rollback: put every file back as the Snapshot saw it, and delete the files that did not exist."""
    for rel_path, data in snapshot.items():
        path = full_path(rel_path)
        if data is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        elif os.path.exists(path):
            os.remove(path)


def apply_patch(patch):
    """Write the Patch to disk and return the paths it touched.

    New contents go to <file>.ioc.tmp first and are swapped in with os.replace only when all of them
    are written, so a file is never left half written. Deletes come last.
    """
    paths = []
    try:
        for entry in patch["files"]:
            if entry["op"] != "delete":
                path = full_path(entry["path"])
                os.makedirs(os.path.dirname(path), exist_ok=True)
                paths.append(path)
                with open(path + ".ioc.tmp", "w", encoding="utf-8") as f:
                    f.write(entry["content"])
        for path in paths:
            os.replace(path + ".ioc.tmp", path)
    except Exception:
        for path in paths:
            if os.path.exists(path + ".ioc.tmp"):
                os.remove(path + ".ioc.tmp")
        raise
    for entry in patch["files"]:
        if entry["op"] == "delete":
            os.remove(full_path(entry["path"]))
    return [entry["path"] for entry in patch["files"]]


def parse_patch(text):
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
        if op not in ("create", "modify", "delete"):
            return None, f"file {number}: op must be create, modify or delete, got {op!r}"
        if op == "delete":
            content = ""
        elif not isinstance(content, str):
            return None, f"file {number}: content must be a string"
        files.append({"path": path, "op": op, "content": content})
    return {"summary": summary, "files": files}, None


PATCH_RULES = f"""Reply with ONLY a JSON object of this shape:
{{"summary": "...", "files": [{{"path": "...", "op": "create" | "modify" | "delete", "content": "..."}}]}}
- content is the COMPLETE new file, not a diff and not only the changed function.
- Use paths exactly as listed under FILES IN THE PROJECT. Use "create" only for a new path.
- Change at most {MAX_FILES} files. Never change ioc.config.yml.
- Do not put "{MARKER}" lines in content.
- Do not write placeholder functions (pass, ..., return None)."""


def build_patch_prompt(intent, k, previous=None):
    """The text for one Attempt. previous is None, or {"patch": the last Patch or None, "error": why it failed}."""
    names = [os.path.relpath(p, index.TARGET_DIR).replace(os.sep, "/") for p in index.list_files(index.TARGET_DIR)]
    parts = ["FILES IN THE PROJECT:\n" + "\n".join(names)]
    # The Chunks only say which files matter; the model gets each of those files whole, once.
    for path in dict.fromkeys(chunk["path"] for chunk in search.search(intent, k)):
        text = read_text(full_path(path))
        if text is not None:
            parts.append(f"{MARKER} {path} ===\n{text}")
    parts.append("INTENT: " + intent)
    parts.append(PATCH_RULES)
    if previous:
        patch = json.dumps(previous["patch"], indent=2) if previous["patch"] else "no valid Patch"
        error = "\n".join(previous["error"].splitlines()[-40:])
        parts.append(f"YOUR PREVIOUS ATTEMPT FAILED.\nYour previous Patch:\n{patch}\nWhy it failed:\n{error}")
    return "\n\n".join(parts)
