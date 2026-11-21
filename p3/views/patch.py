"""POST /patch: run the Patch Loop. Part 3 adds this router to the Part 2 app."""
from fastapi import APIRouter

from p3.schemas.requests import PatchRequest
from p3.schemas.responses import PatchResponse
from p3.services.patch_loop import patch_loop_service


class PatchView:
    def __init__(self, patch_loop_service):
        self.patch_loop_service = patch_loop_service
        self.router = APIRouter()
        self.router.add_api_route("/patch", self.patch, methods=["POST"], response_model=PatchResponse)

    def patch(self, req: PatchRequest):
        """A plain def (not async def), so the server answers other requests meanwhile.

        If the model is unreachable, the LLMError handler in p2/views/errors.py answers 503.
        """
        return self.patch_loop_service.run_patch_loop(req.intent, req.k, req.max_attempts)


patch_view = PatchView(patch_loop_service)
