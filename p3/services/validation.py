"""The Validation Command: the Target Project's own check that it still works after a Patch."""
import os
import shlex
import signal
import subprocess
import sys
import tempfile

import yaml

from p1.config import settings
from p1.repositories import file_repository


def load_validation_command():
    """The Validation Command from the Target Project's ioc.config.yml."""
    with open(file_repository.full_path(settings.VALIDATION_CONFIG), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    command = data.get("validate") if isinstance(data, dict) else None
    if not isinstance(command, str) or not command:
        raise ValueError("ioc.config.yml must contain a 'validate' command")
    return command


def run_validation(changed_files):
    """Run the Validation Command. Return (ok, log)."""
    py_files = [p for p in changed_files if p.endswith(".py") and os.path.isfile(file_repository.full_path(p))]
    # "-" makes py_compile read file names from the (empty) stdin, so it compiles nothing and succeeds
    files_text = " ".join(shlex.quote(p) for p in py_files) or "-"
    command = load_validation_command().replace("{files}", files_text)
    # "python" in the command must be the interpreter that runs this server, even if it is not on PATH
    path = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
    # Python skips recompiling a file whose size and modification second match its old .pyc. After a Rollback
    # that can run the patched code, so validation keeps its .pyc files in a temporary folder, not in the project.
    # For the same reason (nothing new may be left in the project) pytest gets no .pytest_cache folder.
    with tempfile.TemporaryDirectory() as pycache:
        env = dict(os.environ, PATH=path, PYTHONPYCACHEPREFIX=pycache, PYTEST_ADDOPTS="-p no:cacheprovider")
        # Popen, not run: with shell=True, run() on timeout kills only the shell, and pytest keeps running.
        # start_new_session puts the shell and its children in one process group that we can kill together.
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=settings.TARGET_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=env,
            start_new_session=True,
        )
        try:
            log, _ = proc.communicate(timeout=settings.VALIDATION_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return False, f"validation timed out after {settings.VALIDATION_TIMEOUT} seconds"
    return proc.returncode == 0, log
