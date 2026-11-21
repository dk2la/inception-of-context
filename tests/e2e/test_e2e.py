"""End-to-end: the whole system over HTTP, the way a peer drives it at the defense.

Each test follows one requirement of the subject (en.subject v1.1). The server is a real uvicorn process with
the real Index and Watcher; only the model is a scripted fake (see conftest.py). The tests run in file order
and share one server, so each one leaves the Target Project the way it found it, or says what it changed.
"""
import json
import os
import re
import subprocess
import sys

from e2e.conftest import REPO_ROOT, Server, copy_target, tree, wait_until

CORE = "calculator/core.py"


def write(server, rel_path, text):
    path = os.path.join(server.target, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(text, bytes) else "w"
    with open(path, mode) as f:
        f.write(text)
    return path


def read(server, rel_path):
    with open(os.path.join(server.target, rel_path)) as f:
        return f.read()


def ids_by_name(server, path):
    return {c["name"]: c["id"] for c in server.all_chunks() if c["path"] == path}


def indexed(server, rel_path):
    def check():
        return rel_path in server.files()
    check.__name__ = f"{rel_path} to be indexed"
    return wait_until(check)


def gone(server, rel_path):
    def check():
        return rel_path not in server.files()
    check.__name__ = f"{rel_path} to leave the Index"
    return wait_until(check)


def test_p1_overview_reflects_the_target_project(server):
    status = server.http.get("/status").json()
    assert status["target_dir"] == server.target
    assert status["embedding_model"] == "all-MiniLM-L6-v2"
    assert status["answer_model"] == "qwen2.5:3b" and status["patch_model"] == "qwen2.5-coder:3b"
    files = server.files()
    on_disk = {os.path.relpath(os.path.join(root, name), server.target)
               for root, dirs, names in os.walk(server.target) for name in names
               if os.path.getsize(os.path.join(root, name)) > 0}
    assert set(files) == on_disk, "every non-empty file of the Target Project, and nothing else"
    assert sum(files.values()) == status["chunks"] > 0


def test_p1_chunks_follow_the_code_structure_not_a_fixed_size(server):
    file = server.http.get("/file", params={"path": CORE}).json()
    lines = file["content"].splitlines()
    methods = {c["name"]: c for c in file["chunks"] if c["kind"] == "method"}
    assert set(methods) == {"Calculator.add", "Calculator.subtract", "Calculator.multiply", "Calculator.divide"}
    for name, chunk in methods.items():
        assert lines[chunk["start_line"] - 1].strip().startswith("def " + name.split(".")[1])
    assert any(c["kind"] == "class" and c["name"] == "Calculator" for c in file["chunks"])


def test_p1_editing_a_file_reindexes_only_its_changed_chunks_and_streams_an_event(server):
    before = {c["id"] for c in server.all_chunks() if c["path"] != CORE}
    methods_before = ids_by_name(server, CORE)
    original = read(server, CORE)
    try:
        extra = "\n    def negate(self, a):\n        \"\"\"Return -a.\"\"\"\n        return float(-a)\n"
        write(server, CORE, original + extra)
        wait_until(lambda: "Calculator.negate" in ids_by_name(server, CORE))
        after = ids_by_name(server, CORE)
        for name in ["Calculator.add", "Calculator.subtract", "Calculator.multiply", "Calculator.divide"]:
            assert after[name] == methods_before[name], f"{name} did not change, so it keeps its id"
        assert {c["id"] for c in server.all_chunks() if c["path"] != CORE} == before, "other files are untouched"

        with server.http.stream("GET", "/events", timeout=10) as stream:
            for line in stream.iter_lines():
                if line.startswith("data:") and json.loads(line[5:])["path"] == CORE:
                    break
    finally:
        write(server, CORE, original)
        wait_until(lambda: "Calculator.negate" not in ids_by_name(server, CORE))


def test_p1_deleting_a_file_removes_its_chunks(server):
    path = write(server, "extra.py", "def extra():\n    return 1\n")
    indexed(server, "extra.py")
    os.remove(path)
    gone(server, "extra.py")
    assert all(c["path"] != "extra.py" for c in server.all_chunks())


def test_p1_skips_dependency_build_hidden_binary_and_temporary_files(server):
    skipped = ["node_modules/lib.js", ".hidden/secret.py", "build/out.py", "dist/out.py", "venv/x.py",
               "__pycache__/x.py", "blob.bin", "notes.py.ioc.tmp"]
    for rel_path in skipped:
        write(server, rel_path, b"\x00\x01binary" if rel_path.endswith(".bin") else "def nope():\n    return 0\n")
    write(server, "marker.py", "def marker():\n    return 1\n")
    try:
        indexed(server, "marker.py")
        files = server.files()
        assert [p for p in skipped if p in files] == []
    finally:
        for folder in ["node_modules", ".hidden", "build", "dist", "venv", "__pycache__"]:
            subprocess.run(["rm", "-rf", os.path.join(server.target, folder)], check=True)
        for name in ["blob.bin", "notes.py.ioc.tmp", "marker.py"]:
            os.remove(os.path.join(server.target, name))
        gone(server, "marker.py")


def test_p1_the_index_lives_outside_the_target_project(server):
    status = server.http.get("/status").json()
    assert not os.path.realpath(status["chroma_dir"]).startswith(server.target + os.sep)


def test_p1_console_command_indexes_once_and_is_incremental(tmp_path):
    target = copy_target(tmp_path / "target")
    env = dict(os.environ, CHROMA_DIR=str(tmp_path / "chroma"), PYTHONPATH=REPO_ROOT, ANONYMIZED_TELEMETRY="False")
    command = [sys.executable, "-m", "p1.index", target]
    first = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert first.returncode == 0, first.stderr
    match = re.fullmatch(r"indexed (\d+) chunks from (\d+) files\n", first.stdout)
    assert match and int(match[1]) > 0
    second = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert second.stdout == first.stdout, "the Index persisted, and a rescan of the same files changes nothing"


def test_p2_dashboard_has_the_five_tabs_and_needs_no_network(server):
    page = server.http.get("/").text
    for tab in ["Overview", "Files", "ChromaDB Explorer", "Ask &amp; Retrieve", "Patch Loop"]:
        assert tab in page
    assert "http://" not in page and "https://" not in page


def test_p2_context_returns_the_top_k_chunks_with_their_similarity(server):
    results = server.http.post("/context", json={"query": "division by zero", "k": 3}).json()["results"]
    assert len(results) == 3
    assert any("divide" in r["name"] or "zero" in r["text"] for r in results)
    assert all(-1 <= r["similarity"] <= 1 for r in results)
    assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)


def test_p2_symbol_questions_are_answered_from_the_index_without_the_model(server, ollama):
    cases = {
        "is there a function sqrt?": "No.",
        "есть ли функция sqrt?": "No.",
        "is there a function divide?": "Yes.",
    }
    for question, start in cases.items():
        body = server.http.post("/ask", json={"question": question}).json()
        assert body["answer"].startswith(start), question
        assert body["used_llm"] is False
    listed = server.http.post("/ask", json={"question": "what functions are in core.py?"}).json()
    assert listed["answer"] == ("calculator/core.py defines 4 functions: Calculator.add, Calculator.subtract, "
                                "Calculator.multiply, Calculator.divide.")
    assert ollama.prompts == [], "the model was never called"


def test_p2_other_questions_go_to_the_answer_model_grounded_in_known_symbols(server, ollama):
    ollama.replies["qwen2.5:3b"].append("divide raises ZeroDivisionError when b is 0 (calculator/core.py).")
    body = server.http.post("/ask", json={"question": "what happens when I divide by zero?", "k": 4}).json()
    assert body["used_llm"] is True
    assert "ZeroDivisionError" in body["answer"]
    assert len(body["sources"]) == 4
    model, prompt, json_mode = ollama.prompts[0]
    assert model == "qwen2.5:3b" and not json_mode
    assert "KNOWN SYMBOLS" in prompt and "Calculator.divide" in prompt


def test_p2_an_unreachable_model_is_a_clear_503_not_a_crash(server, ollama):
    ollama.status = 500
    response = server.http.post("/ask", json={"question": "explain the cli"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]
    assert server.http.get("/status").status_code == 200


def test_p2_part_2_alone_runs_without_the_patch_loop(tmp_path, ollama):
    target = copy_target(tmp_path / "target")
    alone = Server("p2.app:app", target, str(tmp_path / "chroma"), ollama.url, str(tmp_path / "p2.log"))
    try:
        alone.wait_ready()
        assert "/patch" not in alone.http.get("/openapi.json").json()["paths"]
        assert alone.http.post("/patch", json={"intent": "x"}).status_code in (404, 405)
        answer = alone.http.post("/ask", json={"question": "is there a function add?"}).json()["answer"]
        assert answer.startswith("Yes.")
    finally:
        alone.stop()


def power_patch(server):
    core = read(server, CORE) + ('\n    def power(self, a, b):\n        """Return a ** b."""\n'
                                 '        return float(a ** b)\n')
    test = ("from calculator.core import Calculator\n\n\ndef test_power():\n"
            "    assert Calculator().power(2, 3) == 8.0\n")
    return {"summary": "add power", "files": [
        {"path": CORE, "op": "modify", "content": core},
        {"path": "tests/test_power.py", "op": "create", "content": test},
    ]}


def test_p3_a_good_patch_is_applied_validated_and_reindexed(server, ollama):
    before = tree(server.target)
    original = read(server, CORE)
    ollama.replies["qwen2.5-coder:3b"].append(json.dumps(power_patch(server)))
    try:
        body = server.http.post("/patch", json={"intent": "add a power function to Calculator"}).json()
        assert body["status"] == "success", body
        assert len(body["attempts"]) == 1
        attempt = body["attempts"][0]
        assert attempt["sanity"]["ok"] and attempt["apply"]["ok"] and attempt["validation"]["ok"]
        assert "passed" in attempt["validation"]["log"]
        model, prompt, json_mode = ollama.prompts[0]
        assert model == "qwen2.5-coder:3b" and json_mode
        assert "=== FILE: calculator/core.py ===" in prompt
        assert "def power" in read(server, CORE)
        question = {"question": "is there a function power?"}
        wait_until(lambda: server.http.post("/ask", json=question).json()["answer"].startswith("Yes."))
        assert not [p for p in tree(server.target) if p.endswith(".ioc.tmp")]
    finally:
        os.remove(os.path.join(server.target, "tests/test_power.py"))
        write(server, CORE, original)
    assert tree(server.target) == before


def test_p3_three_failed_attempts_roll_back_byte_for_byte(server, ollama):
    before = tree(server.target)
    broken = json.loads(json.dumps(power_patch(server)))
    broken["files"][0]["content"] = broken["files"][0]["content"].replace("a ** b", "a * b")
    broken["files"].append({"path": "newpkg/deep/helper.py", "op": "create", "content": "X = 1\n"})
    syntax_error = {"summary": "s", "files": [{
        "path": CORE,
        "op": "modify",
        "content": read(server, CORE).replace("return float(a + b)", "return float(a +"),
    }]}
    ollama.replies["qwen2.5-coder:3b"].extend([json.dumps(broken), json.dumps(syntax_error), "this is not json"])

    body = server.http.post("/patch", json={"intent": "add power", "max_attempts": 3}).json()

    assert body["status"] == "failed" and body["patch"] is None
    assert [a["ok"] for a in body["attempts"]] == [False, False, False]
    assert "validation failed" in body["attempts"][0]["error"]
    assert "SyntaxError" in body["attempts"][1]["validation"]["log"]
    assert "valid JSON" in body["attempts"][2]["error"]
    assert "YOUR PREVIOUS ATTEMPT FAILED" in ollama.prompts[1][1] and "validation failed" in ollama.prompts[1][1]
    assert tree(server.target) == before, "every file, and no folder made for a created file"


def test_p3_sanity_checks_refuse_before_anything_touches_the_disk(server, ollama):
    before = tree(server.target)
    refusals = [
        ({"path": CORE, "op": "modify", "content": ""}, "empty"),
        ({"path": "calculator/new.py", "op": "create", "content": "def todo():\n    pass\n"}, "stub function"),
        ({"path": CORE, "op": "create", "content": "x = 1\n"}, "create on existing file"),
        ({"path": "../escape.py", "op": "create", "content": "x = 1\n"}, "outside target"),
        ({"path": "ioc.config.yml", "op": "modify", "content": "validate: true\n"}, "ioc.config.yml"),
        ({"path": "tests/test_core.py", "op": "delete", "content": ""}, "test file"),
        ({"path": CORE, "op": "modify", "content": "class Calculator:\n    pass\n"}, "shrink"),
        ({"path": CORE, "op": "modify", "content": read(server, CORE) + "\n# === FILE: x ===\n"}, "marker"),
    ]
    for entry, reason in refusals:
        ollama.replies["qwen2.5-coder:3b"].append(json.dumps({"summary": "s", "files": [entry]}))
        attempt = server.http.post("/patch", json={"intent": "x", "max_attempts": 1}).json()["attempts"][0]
        assert attempt["sanity"]["ok"] is False and reason in attempt["sanity"]["reason"], (entry, attempt["sanity"])
        assert attempt["apply"] is None
    four = [{"path": f"f{i}.py", "op": "create", "content": "x = 1\n"} for i in range(4)]
    ollama.replies["qwen2.5-coder:3b"].append(json.dumps({"summary": "s", "files": four}))
    attempt = server.http.post("/patch", json={"intent": "x", "max_attempts": 1}).json()["attempts"][0]
    assert "limit is 3" in attempt["sanity"]["reason"]
    assert tree(server.target) == before


def test_p3_an_unreachable_coder_model_is_a_503_and_changes_nothing(server, ollama):
    before = tree(server.target)
    ollama.status = 500
    response = server.http.post("/patch", json={"intent": "add power"})
    assert response.status_code == 503
    assert tree(server.target) == before


def test_the_server_never_contacted_anything_but_the_local_model(server):
    """Everything is local: the only outgoing HTTP calls in the log are to the fake Ollama on 127.0.0.1."""
    log = server.output()
    assert "Traceback" not in log, log[-3000:]
    assert not re.search(r"https?://(?!127\.0\.0\.1)", log.split("Uvicorn running")[0])
