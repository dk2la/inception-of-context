"""Answering Questions, and the one function that talks to the local model."""
import json
import os
import urllib.error
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
ANSWER_MODEL = "qwen2.5:3b"
PATCH_MODEL = "qwen2.5-coder:3b"


class LLMError(Exception):
    pass


def call_llm(model, prompt, json_mode=False):
    """Send a prompt to the local Ollama and return the model's reply as text.

    This is the only place in the project that talks to a model, and it only talks to OLLAMA_HOST.
    """
    body = {"model": model, "prompt": prompt, "stream": False}
    if json_mode:
        body["format"] = "json"
    request = urllib.request.Request(
        OLLAMA_HOST + "/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        # A 3B model on CPU is slow, so the timeout is long.
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())["response"]
    except urllib.error.HTTPError as error:
        raise LLMError(f"Ollama at {OLLAMA_HOST} answered {error.code}: is the model pulled? Run `make models`.")
    except (urllib.error.URLError, TimeoutError) as error:
        raise LLMError(f"Ollama is not reachable at {OLLAMA_HOST}: {error}")
