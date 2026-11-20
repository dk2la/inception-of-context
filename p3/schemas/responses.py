"""The JSON body POST /patch returns."""
from typing import Optional

from pydantic import BaseModel


class AttemptResult(BaseModel):
    number: int
    ok: bool
    error: Optional[str]
    patch: Optional[dict]
    generation: Optional[dict]
    sanity: Optional[dict]
    apply: Optional[dict]
    validation: Optional[dict]


class PatchResponse(BaseModel):
    status: str  # "success" or "failed"
    attempts: list[AttemptResult]
    patch: Optional[dict]
