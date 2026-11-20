"""The one place in the project that talks to a model, and it only talks to the local Ollama."""
import json
import urllib.error
import urllib.request

from p1.config import settings


class LLMError(Exception):
    """The model cannot be reached or refused the request. The API turns it into a 503."""


def call_llm(model, prompt, json_mode=False):
    """Send a prompt to the local Ollama and return the model's reply as text."""
    body = {"model": model, "prompt": prompt, "stream": False}
    if json_mode:
        body["format"] = "json"
    request = urllib.request.Request(
        settings.OLLAMA_HOST + "/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.LLM_TIMEOUT) as response:
            return json.loads(response.read())["response"]
    except urllib.error.HTTPError as error:
        raise LLMError(f"Ollama at {settings.OLLAMA_HOST} answered {error.code}: is the model pulled? Run `make models`.")
    except (urllib.error.URLError, TimeoutError) as error:
        raise LLMError(f"Ollama is not reachable at {settings.OLLAMA_HOST}: {error}")
