"""JSON bodies of the bonus routes."""
from pydantic import BaseModel

from p1.config.settings import settings


class BonusPatchRequest(BaseModel):
    intent: str
    k: int = 5
    max_attempts: int = settings.MAX_ATTEMPTS
    dry_run: bool = False
    git_commit: bool = True


class DockerWatchRequest(BaseModel):
    service: str
    intent: str
