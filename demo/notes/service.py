"""High-level operations on top of Storage with input validation."""
from __future__ import annotations

from .storage import Note, Storage


class NoteService:
    """Public API of the notes app.

    Validates user input, exposes search and tag-filter helpers. Wraps a
    Storage instance so the in-memory state stays trivially swappable.
    """

    def __init__(self, storage: Storage | None = None) -> None:
        self.storage = storage or Storage()

    def create(self, title: str, body: str = "", tags: list[str] | None = None) -> Note:
        title = (title or "").strip()
        if not title:
            raise ValueError("title must not be empty")
        return self.storage.add(title=title, body=body, tags=tags)

    def find(self, note_id: int) -> Note | None:
        return self.storage.get(note_id)

    def search(self, term: str) -> list[Note]:
        term = (term or "").lower()
        if not term:
            return []
        return [n for n in self.storage.list_all()
                if term in n.title.lower() or term in n.body.lower()]

    def by_tag(self, tag: str) -> list[Note]:
        return [n for n in self.storage.list_all() if tag in n.tags]

    def remove(self, note_id: int) -> bool:
        return self.storage.delete(note_id)
