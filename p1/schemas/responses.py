"""The JSON bodies Part 1's routes return. They also document the API at /docs."""
from pydantic import BaseModel


class Status(BaseModel):
    chunks: int
    target_dir: str
    chroma_dir: str
    embedding_model: str
    answer_model: str
    patch_model: str
    ollama_host: str


class FileCount(BaseModel):
    path: str
    chunks: int


class ChunkBounds(BaseModel):
    start_line: int
    end_line: int
    name: str
    kind: str


class FileView(BaseModel):
    path: str
    content: str
    chunks: list[ChunkBounds]


class ChunkRow(ChunkBounds):
    id: str
    text: str
    path: str


class ChunkPage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[ChunkRow]
