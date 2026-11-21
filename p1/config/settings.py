"""Every setting of the project in one place: the Settings class and its one object, settings.

The paths and the Ollama address come from environment variables; the rest are fixed numbers.
Code keeps the settings object and reads settings.NAME when it needs it (never a copy of the value),
so a test or the console command can change it.
"""
import os


class Settings:
    def __init__(self):
        self.TARGET_DIR = os.path.realpath(os.environ.get("TARGET_DIR", "/workspace"))
        self.CHROMA_DIR = os.environ.get("CHROMA_DIR", "/data/chroma")
        self.OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")

        self.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        self.ANSWER_MODEL = "qwen2.5:3b"
        self.PATCH_MODEL = "qwen2.5-coder:3b"
        self.LLM_TIMEOUT = 600

        self.COLLECTION_NAME = "chunks"
        self.SKIPPED_NAMES = {"node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__"}

        self.RRF_K = 60

        self.VALIDATION_CONFIG = "ioc.config.yml"
        self.VALIDATION_TIMEOUT = 60
        self.MAX_ATTEMPTS = 3
        self.MAX_FILES = 3
        self.MAX_SHRINK = 60

    def watch_polling(self):
        """True if WATCH_POLLING=1: Docker bind mounts on macOS and Windows often drop file notifications,
        so the Watcher checks the files itself instead. Read at call time, so it can be switched per run."""
        return os.environ.get("WATCH_POLLING") == "1"


settings = Settings()
