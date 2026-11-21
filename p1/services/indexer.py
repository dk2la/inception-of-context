"""Keep the Index in sync with the Target Project, one file at a time."""
import os

from p1.config.settings import settings
from p1.core.chroma_db import chroma_db
from p1.models.chunk import chunk_factory
from p1.repositories.chunk_repository import chunk_repository
from p1.repositories.file_repository import file_repository
from p1.services.chunker import chunker_service


class IndexerService:
    def __init__(self, settings, chroma_db, chunk_factory, chunk_repository, file_repository, chunker_service):
        self.settings = settings
        self.chroma_db = chroma_db
        self.chunk_factory = chunk_factory
        self.chunk_repository = chunk_repository
        self.file_repository = file_repository
        self.chunker_service = chunker_service

    def reindex_file(self, full_path):
        """Make the Index match one file on disk. Return how many Chunks the file has now.

        A file that is missing, skipped or binary has no Chunks, so its old Chunks are deleted.
        """
        rel_path = self.file_repository.relative_path(full_path)
        if rel_path.startswith(".."):
            return 0

        chunks = []
        text = None if self.file_repository.is_skipped(rel_path) else self.file_repository.read_text(full_path)
        if text is not None:
            chunks = self.chunker_service.chunk_file(rel_path, text)
        new = {self.chunk_factory.chunk_id(rel_path, chunk["text"]): chunk for chunk in chunks}
        old = self.chunk_repository.metadata_by_id(rel_path)

        to_delete = [i for i in old if i not in new]
        to_add = [i for i in new if i not in old]
        moved = [i for i in new if i in old and old[i] != self.chunk_factory.metadata_of(new[i])]
        if to_delete:
            self.chunk_repository.delete(to_delete)
        if to_add:
            texts = [new[i]["text"] for i in to_add]
            self.chunk_repository.add(to_add, texts, [self.chunk_factory.metadata_of(new[i]) for i in to_add])
        if moved:
            self.chunk_repository.update_metadata(moved, [self.chunk_factory.metadata_of(new[i]) for i in moved])
        if to_delete or to_add:
            self.chroma_db.mark_changed()
        return len(new)

    def index_all(self):
        """Make the Index match the whole Target Project. Return the number of Chunks in the Index."""
        on_disk = set()
        for full_path in self.file_repository.list_files(self.settings.TARGET_DIR):
            self.reindex_file(full_path)
            on_disk.add(self.file_repository.relative_path(full_path))

        for rel_path in {m["path"] for m in self.chunk_repository.all_metadata()} - on_disk:
            self.reindex_file(os.path.join(self.settings.TARGET_DIR, rel_path))
        return self.chunk_repository.count()


indexer_service = IndexerService(settings, chroma_db, chunk_factory, chunk_repository, file_repository, chunker_service)
