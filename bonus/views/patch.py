"""POST /bonus/patch: dry-run or the Patch Loop with a diff and an optional git commit."""
from fastapi import APIRouter

from bonus.schemas.requests import BonusPatchRequest
from bonus.services.patch_bonus import patch_bonus_service


class BonusPatchView:
    def __init__(self, patch_bonus_service):
        self.patch_bonus_service = patch_bonus_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/patch", self.patch, methods=["POST"])

    def patch(self, req: BonusPatchRequest):
        return self.patch_bonus_service.run(req.intent, req.k, req.max_attempts, req.dry_run, req.git_commit,
                                            req.pull_request)


bonus_patch_view = BonusPatchView(patch_bonus_service)
