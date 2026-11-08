"""Tiny in-memory notes application used as the IoC target project."""
from .storage import Note, Storage
from .service import NoteService

__all__ = ["Note", "Storage", "NoteService"]
