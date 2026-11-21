"""What the dashboard shows about the Index: status, files, one file with its Chunks, pages of Chunks."""
import os

from p1.config.settings import settings
from p1.repositories.chunk_repository import chunk_repository
from p1.repositories.event_repository import event_repository
from p1.repositories.file_repository import file_repository

CHUNK_FIELDS = ["start_line", "end_line", "name", "kind"]  # what is shown about a Chunk, besides its path


class OverviewService:
    def __init__(self, settings, chunk_repository, event_repository, file_repository):
        # debug: the four collaborators. This service only reads them.
        self.settings = settings
        self.chunk_repository = chunk_repository
        self.event_repository = event_repository
        self.file_repository = file_repository

    def status(self):
        # debug: GET /status. return == {
        #     "chunks": <count()>,                       # how many Chunks are in the Index, an int
        #     "target_dir": "/workspace",
        #     "chroma_dir": "/data/chroma",
        #     "embedding_model": "all-MiniLM-L6-v2",
        #     "answer_model": "qwen2.5:3b",
        #     "patch_model": "qwen2.5-coder:3b",
        #     "ollama_host": "http://ollama:11434",
        # }
        return {
            "chunks": self.chunk_repository.count(),
            "target_dir": self.settings.TARGET_DIR,
            "chroma_dir": self.settings.CHROMA_DIR,
            "embedding_model": self.settings.EMBEDDING_MODEL,
            "answer_model": self.settings.ANSWER_MODEL,
            "patch_model": self.settings.PATCH_MODEL,
            "ollama_host": self.settings.OLLAMA_HOST,
        }

    def files(self):
        """Every file in the Index with its number of Chunks (counted from the Index, not from the disk)."""
        # debug: GET /files. all_metadata() is one dict per Chunk, text is not included.
        # counts == {"README.md": 4, "calculator/core.py": 5, "ioc.config.yml": 1, ...}
        # return == [
        #     {"path": "README.md", "chunks": 4},
        #     {"path": "calculator/core.py", "chunks": 5},
        #     ...
        # ]  # sorted by path. A file that is not in the Index is absent.
        counts = {}
        for meta in self.chunk_repository.all_metadata():
            counts[meta["path"]] = counts.get(meta["path"], 0) + 1
        return [{"path": path, "chunks": counts[path]} for path in sorted(counts)]

    def file_with_chunks(self, path):
        """One file of the Target Project: its content and the Chunk boundaries. None if it may not be shown."""
        # debug: GET /file?path=calculator/core.py
        # "../secrets.txt", ".env", "node_modules/x.js", a missing file → return == None → the route answers 404
        # return == {
        #     "path": "calculator/core.py",
        #     "content": "class Calculator:\n    ...",
        #     "chunks": [
        #         {"start_line": 1,  "end_line": 20, "name": "Calculator",          "kind": "class"},
        #         {"start_line": 4,  "end_line": 6,  "name": "Calculator.add",      "kind": "method"},
        #         {"start_line": 8,  "end_line": 10, "name": "Calculator.subtract", "kind": "method"},
        #         {"start_line": 12, "end_line": 14, "name": "Calculator.multiply", "kind": "method"},
        #         {"start_line": 16, "end_line": 20, "name": "Calculator.divide",   "kind": "method"},
        #     ],
        # }  # no chunk text and no id here. Sorted by start_line.
        if "\x00" in path:  # a NUL byte makes the file functions raise ValueError
            return None
        root = os.path.realpath(self.settings.TARGET_DIR)
        full = os.path.realpath(os.path.join(root, path))  # realpath resolves ".." and symlinks
        rel_path = os.path.relpath(full, root).replace(os.sep, "/")
        # Never trust a path from a request: only files inside the Target Project, and only ones we index.
        if not full.startswith(root + os.sep) or self.file_repository.is_skipped(rel_path):
            return None
        content = self.file_repository.read_text(full)
        if content is None:  # missing, a folder or binary
            return None
        chunks = [{key: meta[key] for key in CHUNK_FIELDS} for meta in self.chunk_repository.metadata_by_id(rel_path).values()]
        chunks.sort(key=lambda chunk: chunk["start_line"])
        return {"path": rel_path, "content": content, "chunks": chunks}

    def chunks_page(self, offset, limit):
        """One page of the Chunks stored in the Index."""
        # debug: GET /chunks. The route calls this with offset == 0, limit == 50 (limit is at most 200).
        # return == {
        #     "total": <count()>, "offset": 0, "limit": 50,
        #     "items": [{
        #         "id": "aa11…",
        #         "text": "    def add(self, a, b):\n        …",
        #         "path": "calculator/core.py",
        #         "start_line": 4, "end_line": 6, "name": "Calculator.add", "kind": "method",
        #     }],
        # }
        items = [{key: chunk[key] for key in ["id", "text", "path"] + CHUNK_FIELDS}
                 for chunk in self.chunk_repository.page(offset, limit)]
        return {"total": self.chunk_repository.count(), "offset": offset, "limit": limit, "items": items}

    def events_since(self, count):
        """The Watcher events after the first count ones."""
        # debug: GET /events polls this every 0.5s. count == 2 means the first two events were already sent.
        # return == [{"time": 1740000000.0, "type": "indexed", "path": "calculator/core.py", "chunks": 5}]
        # nothing new: return == []
        return self.event_repository.events_since(count)


overview_service = OverviewService(settings, chunk_repository, event_repository, file_repository)
