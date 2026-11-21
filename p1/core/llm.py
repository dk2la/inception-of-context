"""The one place in the project that talks to a model, and it only talks to the local Ollama."""
import json
import threading
import time
import urllib.error
import urllib.request

from p1.config.settings import settings


class LLMError(Exception):
    """The model cannot be reached or refused the request. The API turns it into a 503."""


class LLMClient:
    def __init__(self, settings):
        self.settings = settings
        self.live = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def live_snapshot(self):
        """A copy of the latest generation of every model, safe to read while a call is still writing."""
        with self._lock:
            return [dict(state) for state in self.live.values()]

    def _start(self, model):
        with self._lock:
            state = {"id": self._next_id, "model": model, "text": "", "done": False, "error": None,
                     "started": time.time()}
            self._next_id += 1
            self.live[model] = state
            return state

    def _read_stream(self, response, state):
        """Ollama streams one JSON object per line. Append each piece of text as it arrives."""
        for line in response:
            if not line.strip():
                continue
            part = json.loads(line)
            if "error" in part:
                raise LLMError(f"Ollama answered: {part['error']}")
            with self._lock:
                state["text"] += part.get("response", "")
            if part.get("done"):
                break
        return state["text"]

    def call_llm(self, model, prompt, json_mode=False):
        """Send a prompt to the local Ollama and return the model's reply as text.

        The reply is streamed, so the dashboard can show it while the model is still writing (GET /llm/live).
        """
        host = self.settings.OLLAMA_HOST
        body = {"model": model, "prompt": prompt, "stream": True}
        if json_mode:
            body["format"] = "json"
        request = urllib.request.Request(
            host + "/api/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        state = self._start(model)
        try:
            with urllib.request.urlopen(request, timeout=self.settings.LLM_TIMEOUT) as response:
                return self._read_stream(response, state)
        except urllib.error.HTTPError as error:
            state["error"] = f"Ollama at {host} answered {error.code}: is the model pulled? Run `make models`."
            raise LLMError(state["error"])
        except (urllib.error.URLError, TimeoutError) as error:
            state["error"] = f"Ollama is not reachable at {host}: {error}"
            raise LLMError(state["error"])
        except LLMError as error:
            state["error"] = str(error)
            raise
        finally:
            state["done"] = True


llm_client = LLMClient(settings)
