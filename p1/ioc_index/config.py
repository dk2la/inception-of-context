"""Runtime settings, read once from the environment.

Every value has a sane default so `python p1/index.py ./demo` works out of the box.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass
class Settings:
    target: Path
    chroma_path: Path
    collection: str = "ioc"
    embedder: str = "onnx-minilm"          # "onnx-minilm" (all-MiniLM-L6-v2) or "fake" (tests)
    embed_model_name: str = "all-MiniLM-L6-v2"
    embed_cache: Path | None = None
    watch_mode: str = "auto"               # auto | native | polling | off
    poll_interval: float = 1.0
    debounce: float = 0.4
    max_file_bytes: int = 512 * 1024
    ollama_url: str = "http://localhost:11434"
    ask_model: str = "qwen2.5:3b"
    code_model: str = "qwen2.5-coder:3b"
    host: str = "0.0.0.0"
    port: int = 8000
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, target: str | os.PathLike | None = None, **overrides) -> "Settings":
        tgt = Path(target or _env("IOC_TARGET", "./demo")).expanduser().resolve()
        chroma = Path(_env("IOC_CHROMA_PATH", str(Path.cwd() / ".ioc-data" / "chroma"))).expanduser().resolve()
        cache = os.environ.get("IOC_EMBED_CACHE")
        s = cls(
            target=tgt,
            chroma_path=chroma,
            collection=_env("IOC_COLLECTION", "ioc"),
            embedder=_env("IOC_EMBEDDER", "onnx-minilm"),
            embed_cache=Path(cache).expanduser().resolve() if cache else None,
            watch_mode=_env("IOC_WATCH_MODE", "auto"),
            poll_interval=float(_env("IOC_POLL_INTERVAL", "1.0")),
            debounce=float(_env("IOC_DEBOUNCE", "0.4")),
            ollama_url=_env("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            ask_model=_env("IOC_ASK_MODEL", "qwen2.5:3b"),
            code_model=_env("IOC_CODE_MODEL", "qwen2.5-coder:3b"),
            host=_env("IOC_HOST", "0.0.0.0"),
            port=int(_env("IOC_PORT", "8000")),
        )
        for key, value in overrides.items():
            if value is not None:
                setattr(s, key, value)
        return s
