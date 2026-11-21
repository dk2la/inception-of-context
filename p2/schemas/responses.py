"""The JSON bodies Part 2's routes return. They also document the API at /docs."""
from typing import Optional

from pydantic import BaseModel

from p1.schemas.responses import ChunkRow


class Source(ChunkRow):
    """A Chunk used for an answer. similarity and score exist only when it came from retrieval."""
    hash: str
    similarity: Optional[float] = None
    score: Optional[float] = None


class ContextResponse(BaseModel):
    results: list[Source]


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    used_llm: bool
