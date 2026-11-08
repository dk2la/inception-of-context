import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from ioc_api.llm import ScriptedLLM
from ioc_api.server import attach_services
from ioc_bonus.diffs import file_diff
from ioc_bonus.server import BonusPatchLoop, create_app


@pytest.fixture
def setup(ctx, target):
    ctx.indexer.full_sync()
    llm = ScriptedLLM()
    attach_services(ctx, llm=llm)
    return TestClient(create_app(ctx, start=False)), llm, target


def patch_json(target, extra="\n\nX = 1\n"):
    return json.dumps({"summary": "add X", "files": [
        {"path": "main.py", "op": "modify", "content": (target / "main.py").read_text() + extra}]})


def test_reindex(setup, ctx):
    client, _, _ = setup
    d = client.post("/reindex").json()
    assert d["chunks"] == ctx.store.count() and d["added"] == 0
    d = client.post("/reindex?reset=true").json()
    assert d["added"] == d["chunks"] > 0


def test_dry_run_never_writes(setup):
    client, llm, target = setup
    before = (target / "main.py").read_bytes()
    llm.replies = [patch_json(target)]
    d = client.post("/patch/dry-run", json={"intent": "add X"}).json()
    assert d["ok"] and d["diff"][0]["added"] == 3 and "+X = 1" in d["diff"][0]["diff"]
    assert (target / "main.py").read_bytes() == before


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_success_has_diff_and_autocommit(setup, monkeypatch):
    client, llm, target = setup
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], cwd=target, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=target, check=True)
    monkeypatch.setattr(BonusPatchLoop, "autocommit", True)
    llm.replies = [patch_json(target), "Add X constant to main module"]
    r = client.post("/patch/run", json={"intent": "add X"}).json()
    assert r["status"] == "success" and r["diff"][0]["path"] == "main.py"
    assert r["git"]["ok"] and r["git"]["message"] == "Add X constant to main module"
    log = client.get("/git").json()
    assert log["repo"] and log["log"][0]["subject"] == "Add X constant to main module"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True).stdout
    assert status.strip() == ""


def test_autocommit_skips_non_repo(setup, monkeypatch):
    client, llm, target = setup
    monkeypatch.setattr(BonusPatchLoop, "autocommit", True)
    llm.replies = [patch_json(target), "msg"]
    r = client.post("/patch/run", json={"intent": "add X"}).json()
    assert r["status"] == "success" and r["git"]["skipped"]


def test_file_diff_create_delete():
    assert file_diff("a.py", None, "x = 1\n").startswith("--- /dev/null")
    assert "+++ /dev/null" in file_diff("a.py", "x = 1\n", None)
