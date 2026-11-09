"""The Patch Loop: the small steps it is built from (config, validate, snapshot, apply, parse)."""
import os
import shlex
import signal
import subprocess
import sys

import yaml

from p1 import index

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
        env=dict(os.environ, PATH=path),
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
