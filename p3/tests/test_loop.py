import json
import os

import pytest
from fastapi.testclient import TestClient

from ioc_api.llm import ScriptedLLM
from ioc_api.server import attach_services
from ioc_patch.server import create_app


def snapshot_tree(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ("__pycache__",)]
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root)] = open(p, "rb").read()
    return out


@pytest.fixture
def setup(ctx, target):
    ctx.indexer.full_sync()
    llm = ScriptedLLM()
    attach_services(ctx, llm=llm)
    client = TestClient(create_app(ctx, start=False))
    return client, llm, target


def as_json(files, summary="change"):
    return json.dumps({"summary": summary, "files": files})


def main_with(target, extra):
    return (target / "main.py").read_text() + extra


def test_success_first_try(setup, ctx):
    client, llm, target = setup
    llm.replies = [as_json([{"path": "main.py", "op": "modify",
                             "content": main_with(target, "\n\ndef whisper(name: str) -> str:\n    return greet(name).lower()\n")}])]
    r = client.post("/patch/run", json={"intent": "add whisper(name) to main.py", "k": 3}).json()
    assert r["status"] == "success" and r["attempt_count"] == 1
    assert [s["stage"] for s in r["attempts"][0]["steps"]] == ["generate", "sanity", "apply", "validate"]
    assert "def whisper" in (target / "main.py").read_text()
    assert any(m["symbol"] == "whisper" for m in ctx.store.file_chunks("main.py").values())   # reindexed
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "<<<IOC_FILE main.py>>>" in prompt and "CHANGE REQUEST" in prompt
    assert llm.calls[0]["json_mode"] is True


def test_sanity_refusal_then_fix(setup):
    client, llm, target = setup
    llm.replies = [
        as_json([{"path": "main.py", "op": "modify", "content": main_with(target, "\n\ndef whisper(name):\n    pass\n")}]),
        as_json([{"path": "main.py", "op": "modify", "content": main_with(target, "\n\ndef whisper(name):\n    return name.lower()\n")}]),
    ]
    r = client.post("/patch/run", json={"intent": "add whisper"}).json()
    assert r["status"] == "success" and r["attempt_count"] == 2
    assert r["attempts"][0]["steps"][1]["stage"] == "sanity" and not r["attempts"][0]["steps"][1]["ok"]
    feedback = llm.calls[1]["messages"][-1]["content"]
    assert "sanity" in feedback and "stub" in feedback


def test_validation_failure_three_times_rolls_back_exactly(setup, ctx):
    client, llm, target = setup
    before = snapshot_tree(target)
    broken = as_json([
        {"path": "main.py", "op": "modify", "content": main_with(target, "\n\ndef broken(:\n    return 1\n")},
        {"path": "notes/new_mod.py", "op": "create", "content": "VALUE = 1\n"},
        {"path": "notes/cli.py", "op": "delete"},
    ])
    llm.replies = [broken, broken, "not even json"]
    r = client.post("/patch/run", json={"intent": "break things"}).json()
    assert r["status"] == "rolled_back" and r["attempt_count"] == 3 and r["rollback_verified"] is True
    assert snapshot_tree(target) == before
    assert "SyntaxError" in llm.calls[1]["messages"][-1]["content"]
    assert ctx.store.file_chunks("notes/new_mod.py") == {} and ctx.store.file_chunks("notes/cli.py")


def test_failing_tests_are_fed_back(setup):
    client, llm, target = setup
    bad = (target / "main.py").read_text().replace('return f"Hello, {name}!"', 'return f"Hi, {name}!"')
    good = main_with(target, "\n\ndef hi(name: str) -> str:\n    return f\"Hi, {name}!\"\n")
    llm.replies = [as_json([{"path": "main.py", "op": "modify", "content": bad}]),
                   as_json([{"path": "main.py", "op": "modify", "content": good}])]
    r = client.post("/patch/run", json={"intent": "say hi"}).json()
    assert r["status"] == "success" and r["attempt_count"] == 2
    assert "test_greetings" in llm.calls[1]["messages"][-1]["content"]
    assert r["attempts"][0]["steps"][-1]["stage"] == "rollback"


def test_max_attempts_and_validation(setup):
    client, llm, _ = setup
    assert client.post("/patch/run", json={"intent": "x", "max_attempts": 4}).status_code == 422
    assert client.post("/patch/run", json={"intent": ""}).status_code == 422
    llm.replies = ["{}"]
    r = client.post("/patch/run", json={"intent": "x", "max_attempts": 1}).json()
    assert r["status"] == "rolled_back" and r["attempt_count"] == 1


def test_llm_unavailable_is_reported_and_nothing_changes(setup):
    client, llm, target = setup
    before = snapshot_tree(target)
    r = client.post("/patch/run", json={"intent": "anything"}).json()          # no scripted reply -> LLMError
    assert r["status"] == "error" and snapshot_tree(target) == before


def test_streaming_ndjson(setup):
    client, llm, target = setup
    llm.replies = [as_json([{"path": "main.py", "op": "modify", "content": main_with(target, "\n\nX = 1\n")}])]
    with client.stream("POST", "/patch/run", json={"intent": "add X", "stream": True}) as resp:
        events = [json.loads(line) for line in resp.iter_lines() if line]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done" and kinds.count("step") == 4
    assert events[-1]["result"]["status"] == "success"
    hist = client.get("/patch/history").json()
    assert hist["runs"][0]["status"] == "success"


def test_generate_only_writes_nothing(setup):
    client, llm, target = setup
    before = snapshot_tree(target)
    llm.replies = [as_json([{"path": "main.py", "op": "create", "content": "x = 1\n"}])]
    r = client.post("/patch/generate", json={"intent": "x"}).json()
    assert r["ok"] is False and "already exists" in r["violations"][0]
    assert snapshot_tree(target) == before
