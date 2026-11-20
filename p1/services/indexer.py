"""Keep the Index in sync with the Target Project, one file at a time."""
import os

from p1.config import settings
from p1.core import database
from p1.models.chunk import chunk_id, metadata_of
from p1.repositories import chunk_repository, file_repository
from p1.services.chunker import chunk_file


def reindex_file(full_path):
    """Make the Index match one file on disk. Return how many Chunks the file has now.

    A file that is missing, skipped or binary has no Chunks, so its old Chunks are deleted.
    """
    rel_path = file_repository.relative_path(full_path)
    if rel_path.startswith(".."):
        return 0  # outside the Target Project

    chunks = []
    text = None if file_repository.is_skipped(rel_path) else file_repository.read_text(full_path)
    if text is not None:
        chunks = chunk_file(rel_path, text)
    new = {chunk_id(rel_path, chunk["text"]): chunk for chunk in chunks}
    old = chunk_repository.metadata_by_id(rel_path)

    to_delete = [i for i in old if i not in new]
    to_add = [i for i in new if i not in old]
    # Same text, but the lines moved (something above it changed): update the numbers only.
    moved = [i for i in new if i in old and old[i] != metadata_of(new[i])]
    if to_delete:
        chunk_repository.delete(to_delete)
    if to_add:
        chunk_repository.add(to_add, [new[i]["text"] for i in to_add], [metadata_of(new[i]) for i in to_add])
    if moved:
        chunk_repository.update_metadata(moved, [metadata_of(new[i]) for i in moved])
    if to_delete or to_add:  # the keyword index holds only the texts, so moved Chunks do not change it
        database.mark_changed()
    return len(new)


def index_all():
    """Make the Index match the whole Target Project. Return the number of Chunks in the Index."""
    on_disk = set()
    for full_path in file_repository.list_files(settings.TARGET_DIR):
        reindex_file(full_path)
        on_disk.add(file_repository.relative_path(full_path))

    # Files deleted while nobody was watching are only in the Index: reindexing them removes them.
    for rel_path in {m["path"] for m in chunk_repository.all_metadata()} - on_disk:
        reindex_file(os.path.join(settings.TARGET_DIR, rel_path))
    return chunk_repository.count()
