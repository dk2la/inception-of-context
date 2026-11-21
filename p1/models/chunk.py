"""The Chunk: one logical block of a file (a function, a class, a YAML key, ...).

A Chunk is a plain dict; the TypedDict below only documents its keys, and ChunkFactory makes them.
"""
import hashlib
from typing import TypedDict


class Chunk(TypedDict):
    path: str  # relative to the Target Project, with forward slashes
    start_line: int  # first line (1-based, inclusive)
    end_line: int  # last line (1-based, inclusive)
    name: str  # symbol name; methods are "Class.method", the module header is "<module>"
    kind: str  # function, async_function, class, method, module, yaml_key, heading or definition
    text: str  # the exact source text
    hash: str  # SHA-256 (hex) of text


METADATA_KEYS = ["path", "start_line", "end_line", "name", "kind", "hash"]  # stored next to the text
SYMBOL_KINDS = ["function", "async_function", "class", "method"]  # the kinds that are real symbols


class ChunkFactory:
    """Makes Chunks, their ids and what the Index stores about them."""

    def make_chunk(self, path, start_line, end_line, name, kind, text):
        """Return one Chunk."""
        return {
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "name": name,
            "kind": kind,
            "text": text,
            "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    def chunk_id(self, path, text):
        """An id computed from the Chunk itself: the same path and text always give the same id."""
        return hashlib.sha256((path + "\n" + text).encode("utf-8")).hexdigest()

    def metadata_of(self, chunk):
        """What the Index stores next to the text of a Chunk."""
        return {key: chunk[key] for key in METADATA_KEYS}


chunk_factory = ChunkFactory()
