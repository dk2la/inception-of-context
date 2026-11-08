"""Runs the target's own validation command, configured in <target>/ioc.config.yml."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

DEFAULT_COMMAND = "python -m py_compile {py_files}"
DEFAULT_TIMEOUT = 120
CONFIG_NAMES = ("ioc.config.yml", "ioc.config.yaml")


def load_config(target: Path) -> dict:
    for name in CONFIG_NAMES:
        p = target / name
        if p.is_file():
            data = yaml.safe_load(p.read_text()) or {}
            break
    else:
        data = {}
    v = data.get("validate", {}) if isinstance(data, dict) else {}
    if isinstance(v, str):
        v = {"command": v}
    elif isinstance(v, list):
        v = {"commands": v}
    commands = v.get("commands") or [v.get("command") or DEFAULT_COMMAND]
    return {"commands": [str(c) for c in commands], "timeout": int(v.get("timeout", DEFAULT_TIMEOUT))}


def render(command: str, files: list[str]) -> str:
    py = [f for f in files if f.endswith((".py", ".pyi"))]
    return (command.replace("{py_files}", " ".join(shlex.quote(f) for f in py))
                   .replace("{files}", " ".join(shlex.quote(f) for f in files)))


def run_validation(target: Path, touched: list[str]) -> dict:
    cfg = load_config(target)
    existing = [f for f in touched if (target / f).is_file()]
    # `python` in the command resolves to the interpreter running IoC (venv or container), and
    # bytecode goes to a temp prefix so validation never writes __pycache__ into the target.
    env = dict(os.environ, PYTHONPYCACHEPREFIX=os.path.join(tempfile.gettempdir(), "ioc-pycache"),
               PYTHONDONTWRITEBYTECODE="1",
               PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
    t0 = time.time()
    log, ok, code, ran = [], True, 0, []
    for raw in cfg["commands"]:
        cmd = render(raw, existing)
        ran.append(cmd)
        try:
            proc = subprocess.run(cmd, shell=True, cwd=target, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=cfg["timeout"])
            code = proc.returncode
            out = (proc.stdout + proc.stderr).strip()
        except subprocess.TimeoutExpired as exc:
            code, out = 124, f"validation timed out after {cfg['timeout']}s\n{(exc.stdout or '')}"
        log.append(f"$ {cmd}\n{out}".strip())
        if code != 0:
            ok = False
            break
    output = "\n\n".join(log)
    if len(output) > 6000:
        output = "…(truncated)…\n" + output[-6000:]
    return {"ok": ok, "exit_code": code, "commands": ran, "output": output, "seconds": round(time.time() - t0, 2)}
