"""JSON bodies of the bonus routes."""
from pydantic import BaseModel

from p1.config.settings import settings


class BonusPatchRequest(BaseModel):
    # debug: POST /bonus/patch
    # {"intent": "add a power function to Calculator", "k": 5, "max_attempts": 3,
    #  "dry_run": false, "git_commit": true, "pull_request": false}
    # a body with only "intent" keeps k == 5, max_attempts == 3, dry_run == False, git_commit == True,
    # pull_request == False (a green Patch stays on disk, as before)
    intent: str
    k: int = 5
    max_attempts: int = settings.MAX_ATTEMPTS
    dry_run: bool = False
    git_commit: bool = True
    pull_request: bool = False


class MergeRequest(BaseModel):
    # debug: POST /bonus/pulls/1/merge {"git_commit": true}. An empty body commits too.
    git_commit: bool = True


class DockerWatchRequest(BaseModel):
    # debug: POST /bonus/docker/watch {"service": "calculator", "intent": "fix the crash in Calculator.divide"}
    service: str
    intent: str
