"""POST /bonus/patch: dry-run or the Patch Loop with a diff and an optional git commit."""
from fastapi import APIRouter

from bonus.schemas.requests import BonusPatchRequest
from bonus.services.patch_bonus import patch_bonus_service


class BonusPatchView:
    def __init__(self, patch_bonus_service):
        # debug: one route, POST /bonus/patch. The body is a BonusPatchRequest.
        self.patch_bonus_service = patch_bonus_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/patch", self.patch, methods=["POST"])

    def patch(self, req: BonusPatchRequest):
        # debug: req.intent == "add a power function to Calculator", req.k == 5, req.max_attempts == 3
        # req.dry_run == False, req.git_commit == True. return is the dict from patch_bonus_service.run.
        return self.patch_bonus_service.run(req.intent, req.k, req.max_attempts, req.dry_run, req.git_commit,
                                            req.pull_request)


bonus_patch_view = BonusPatchView(patch_bonus_service)
