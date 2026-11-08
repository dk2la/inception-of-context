"""Minimal client for a local Ollama server. Nothing here ever talks to a remote LLM."""
from __future__ import annotations

import time

import httpx


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, model: str, messages: list[dict], *, json_mode: bool = False,
             temperature: float = 0.1, num_ctx: int = 8192, num_predict: int | None = None) -> str:
        options = {"temperature": temperature, "num_ctx": num_ctx}
        if num_predict:
            options["num_predict"] = num_predict
        payload = {"model": model, "messages": messages, "stream": False, "options": options}
        if json_mode:
            payload["format"] = "json"
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"cannot reach Ollama at {self.base_url}: {exc}") from exc
        if r.status_code == 404:
            raise LLMError(f"model '{model}' is not available in Ollama (run `make models`)")
        if r.status_code >= 400:
            raise LLMError(f"Ollama error {r.status_code}: {r.text[:300]}")
        return r.json().get("message", {}).get("content", "")

    def models(self) -> list[str]:
        r = httpx.get(f"{self.base_url}/api/tags", timeout=10)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))

    def health(self) -> dict:
        t0 = time.time()
        try:
            models = self.models()
            return {"ok": True, "url": self.base_url, "models": models, "latency_ms": int((time.time() - t0) * 1000)}
        except Exception as exc:
            return {"ok": False, "url": self.base_url, "error": str(exc)}


class ScriptedLLM:
    """Test double: returns canned answers (or calls a function) and records the prompts."""

    def __init__(self, replies=None) -> None:
        self.replies = list(replies or [])
        self.calls: list[dict] = []
        self.base_url = "scripted://"

    def chat(self, model, messages, **kw) -> str:
        self.calls.append({"model": model, "messages": messages, **kw})
        if not self.replies:
            raise LLMError("no scripted reply left")
        reply = self.replies.pop(0)
        return reply(messages) if callable(reply) else reply

    def models(self) -> list[str]:
        return ["scripted"]

    def health(self) -> dict:
        return {"ok": True, "url": self.base_url, "models": ["scripted"]}
