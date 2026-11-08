"""Low-level storage for notes: an in-memory dictionary keyed by id."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Note:
    """A single note with a title, a body and a list of tags."""

    id: int
    title: str
    body: str = ""
    tags: list[str] = field(default_factory=list)


class Storage:
    """Keeps notes in memory and hands out incremental ids."""

    def __init__(self) -> None:
        self._notes: dict[int, Note] = {}
        self._next_id = 1

    def add(self, title: str, body: str = "", tags: list[str] | None = None) -> Note:
        note = Note(id=self._next_id, title=title, body=body, tags=list(tags or []))
        self._notes[note.id] = note
        self._next_id += 1
        return note

    def get(self, note_id: int) -> Note | None:
        return self._notes.get(note_id)

    def list_all(self) -> list[Note]:
        return sorted(self._notes.values(), key=lambda n: n.id)

    def delete(self, note_id: int) -> bool:
        return self._notes.pop(note_id, None) is not None

    def count(self) -> int:
        return len(self._notes)
