"""What the dashboard shows about the Index: status, files, one file with its Chunks, pages of Chunks."""
import os

from p1.config.settings import settings
from p1.repositories.chunk_repository import chunk_repository
from p1.repositories.event_repository import event_repository
from p1.repositories.file_repository import file_repository

CHUNK_FIELDS = ["start_line", "end_line", "name", "kind"]  # what is shown about a Chunk, besides its path


class OverviewService:
    def __init__(self, settings, chunk_repository, event_repository, file_repository):
        self.settings = settings
        self.chunk_repository = chunk_repository
        self.event_repository = event_repository
        self.file_repository = file_repository

    def status(self):
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
        counts = {}
        for meta in self.chunk_repository.all_metadata():
            counts[meta["path"]] = counts.get(meta["path"], 0) + 1
        return [{"path": path, "chunks": counts[path]} for path in sorted(counts)]

    def file_with_chunks(self, path):
        """One file of the Target Project: its content and the Chunk boundaries. None if it may not be shown."""
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
        items = [{key: chunk[key] for key in ["id", "text", "path"] + CHUNK_FIELDS}
                 for chunk in self.chunk_repository.page(offset, limit)]
        return {"total": self.chunk_repository.count(), "offset": offset, "limit": limit, "items": items}

    def events_since(self, count):
        """The Watcher events after the first count ones."""
        return self.event_repository.events_since(count)


overview_service = OverviewService(settings, chunk_repository, event_repository, file_repository)
