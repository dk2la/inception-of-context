"""Every setting of the project in one place: the Settings class and its one object, settings.

The paths and the Ollama address come from environment variables; the rest are fixed numbers.
Code keeps the settings object and reads settings.NAME when it needs it (never a copy of the value),
so a test or the console command can change it.
"""
import os


class Settings:
    def __init__(self):
        # Where things are
        # realpath: the Watcher gets real paths from the system (on macOS /tmp is /private/tmp), and a path
        # through a symlink would never match them, so every change would be ignored.
        self.TARGET_DIR = os.path.realpath(os.environ.get("TARGET_DIR", "/workspace"))  # the Target Project
        self.CHROMA_DIR = os.environ.get("CHROMA_DIR", "/data/chroma")  # the Index, outside the Target Project
        self.OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")  # the local model server

        # The local models
        self.EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Chroma's built-in embedder (ONNX), downloaded once at image build
        self.ANSWER_MODEL = "qwen2.5:3b"  # answers Questions
        self.PATCH_MODEL = "qwen2.5-coder:3b"  # writes Patches
        self.LLM_TIMEOUT = 600  # seconds; a 3B model on CPU is slow

        # Index
        self.COLLECTION_NAME = "chunks"
        # Folders we never index. Hidden files and folders (starting with ".") are skipped too.
        self.SKIPPED_NAMES = {"node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__"}

        # Retrieval
        self.RRF_K = 60  # the usual constant: a Chunk far down one list still gets a little from it

        # Patch Loop
        self.VALIDATION_CONFIG = "ioc.config.yml"  # the Target Project's file that holds the Validation Command
        self.VALIDATION_TIMEOUT = 60  # seconds
        self.MAX_ATTEMPTS = 3  # the model gets three tries, then the Patch Loop gives up
        self.MAX_FILES = 3  # a Patch may touch at most this many files
        self.MAX_SHRINK = 60  # percent: a modify may not cut a file by more than this

    def watch_polling(self):
        """True if WATCH_POLLING=1: Docker bind mounts on macOS and Windows often drop file notifications,
        so the Watcher checks the files itself instead. Read at call time, so it can be switched per run."""
        return os.environ.get("WATCH_POLLING") == "1"


settings = Settings()
