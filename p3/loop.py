"""The Patch Loop: the small steps it is built from (config, validate, snapshot, apply, parse)."""
import os
import shlex
import subprocess
import sys

import yaml

from p1 import index


def load_validation_command():
    """The Validation Command from the Target Project's ioc.config.yml."""
    with open(os.path.join(index.TARGET_DIR, "ioc.config.yml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict) or not isinstance(config.get("validate"), str) or not config["validate"]:
        raise ValueError("ioc.config.yml must contain a 'validate' command")
    return config["validate"]


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
    result = subprocess.run(
        command,
        shell=True,
        cwd=index.TARGET_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        env=dict(os.environ, PATH=path),
    )
    return result.returncode == 0, result.stdout
