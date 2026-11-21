"""End-to-end fixtures: a real server process over a copy of the Target Project, and a scripted fake Ollama.

Nothing here is mocked inside the server: it is started with uvicorn exactly like in the container, with its own
Chroma folder and the real Watcher. Only the model is replaced, by a tiny HTTP server that speaks Ollama's
/api/generate and answers from a script, so the tests are fast, repeatable and never need a real model.
"""
import collections
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_TARGET = os.environ.get("TARGET_DIR") or os.path.join(REPO_ROOT, "target")


def wait_until(condition, seconds=60, every=0.25):
    """Call condition until it returns something truthy; return that, or fail after seconds."""
    end = time.time() + seconds
    while time.time() < end:
        result = condition()
        if result:
            return result
        time.sleep(every)
    raise AssertionError(f"timed out after {seconds}s waiting for {condition.__name__}")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def tree(folder):
    """{relative path: sha256} of every file and folder under folder, to prove it is byte for byte the same."""
    found = {}
    for root, dirs, names in os.walk(folder):
        for name in dirs:
            found[os.path.relpath(os.path.join(root, name), folder) + "/"] = "dir"
        for name in names:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                found[os.path.relpath(path, folder)] = hashlib.sha256(f.read()).hexdigest()
    return found


class FakeOllama:
    """Answers POST /api/generate from a script: replies[model] is a queue of texts. Records every prompt."""

    def __init__(self):
        self.replies = collections.defaultdict(collections.deque)
        self.prompts = []
        self.status = 200
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.prompts.append((body["model"], body["prompt"], body.get("format") == "json"))
                queue = fake.replies[body["model"]]
                if fake.status != 200 or not queue:
                    self.send_response(fake.status if fake.status != 200 else 500)
                    self.end_headers()
                    return
                data = json.dumps({"response": queue.popleft(), "done": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def reset(self):
        self.replies.clear()
        self.prompts.clear()
        self.status = 200


class Server:
    """One uvicorn process serving an app of this repository."""

    def __init__(self, app, target, chroma, ollama_url, log_path):
        self.port = free_port()
        self.target = target
        self.log_path = log_path
        env = dict(os.environ, TARGET_DIR=target, CHROMA_DIR=chroma, OLLAMA_HOST=ollama_url,
                   PYTHONPATH=REPO_ROOT, PYTHONDONTWRITEBYTECODE="1", ANONYMIZED_TELEMETRY="False")
        env.pop("WATCH_POLLING", None)
        self.log = open(log_path, "w")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", app, "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=REPO_ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=180)

    def output(self):
        with open(self.log_path) as f:
            return f.read()

    def wait_ready(self):
        """Up, and the Watcher started after the first indexing (it prints "watching ...")."""
        def ready():
            assert self.process.poll() is None, "the server died:\n" + self.output()
            return "watching" in self.output()
        wait_until(ready, seconds=120)

    def stop(self):
        self.http.close()
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()

    def files(self):
        return {f["path"]: f["chunks"] for f in self.http.get("/files").json()}

    def all_chunks(self):
        chunks, offset = [], 0
        while True:
            page = self.http.get("/chunks", params={"offset": offset, "limit": 200}).json()
            chunks += page["items"]
            offset += 200
            if offset >= page["total"]:
                return chunks


def copy_target(destination):
    shutil.copytree(REAL_TARGET, destination, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return os.path.realpath(destination)


@pytest.fixture(scope="module")
def ollama():
    fake = FakeOllama()
    yield fake
    fake.server.shutdown()


@pytest.fixture(scope="module")
def server(tmp_path_factory, ollama):
    """The full system (p3.app, what the container runs) over a fresh copy of the Target Project."""
    base = tmp_path_factory.mktemp("e2e")
    target = copy_target(base / "target")
    running = Server("p3.app:app", target, str(base / "chroma"), ollama.url, str(base / "server.log"))
    running.wait_ready()
    yield running
    running.stop()


@pytest.fixture(autouse=True)
def fresh_model_script(request):
    """Every test starts with an empty model script."""
    if "ollama" in request.fixturenames:
        request.getfixturevalue("ollama").reset()
