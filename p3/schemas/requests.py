"""The JSON body POST /patch accepts."""
from pydantic import BaseModel

from p1.config.settings import settings


class PatchRequest(BaseModel):
    intent: str
    k: int = 5
    max_attempts: int = settings.MAX_ATTEMPTS
