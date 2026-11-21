"""The Validation Command: the Target Project's own check that it still works after a Patch."""
import os
import shlex
import signal
import subprocess
import sys
import tempfile

import yaml

from p1.config.settings import settings
from p1.repositories.file_repository import file_repository


class ValidationService:
    def __init__(self, settings, file_repository):
        self.settings = settings
        self.file_repository = file_repository

    def load_validation_command(self):
        """The Validation Command from the Target Project's ioc.config.yml."""
        with open(self.file_repository.full_path(self.settings.VALIDATION_CONFIG), encoding="utf-8") as f:
            data = yaml.safe_load(f)
        command = data.get("validate") if isinstance(data, dict) else None
        if not isinstance(command, str) or not command:
            raise ValueError("ioc.config.yml must contain a 'validate' command")
        return command

    def run_validation(self, changed_files):
        """Run the Validation Command. Return (ok, log)."""
        py_files = [p for p in changed_files if p.endswith(".py") and os.path.isfile(self.file_repository.full_path(p))]
        files_text = " ".join(shlex.quote(p) for p in py_files) or "-"
        command = self.load_validation_command().replace("{files}", files_text)
        path = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
        with tempfile.TemporaryDirectory() as pycache:
            env = dict(os.environ, PATH=path, PYTHONPYCACHEPREFIX=pycache, PYTEST_ADDOPTS="-p no:cacheprovider")
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=self.settings.TARGET_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                env=env,
                start_new_session=True,
            )
            try:
                log, _ = proc.communicate(timeout=self.settings.VALIDATION_TIMEOUT)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                return False, f"validation timed out after {self.settings.VALIDATION_TIMEOUT} seconds"
        return proc.returncode == 0, log


validation_service = ValidationService(settings, file_repository)
