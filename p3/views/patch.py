"""POST /patch: run the Patch Loop. Part 3 adds this router to the Part 2 app."""
from fastapi import APIRouter

from p3.schemas.requests import PatchRequest
from p3.schemas.responses import PatchResponse
from p3.services import patch_loop

router = APIRouter()


@router.post("/patch", response_model=PatchResponse)
def patch(req: PatchRequest):
    """A plain def (not async def), so the server answers other requests meanwhile.

    If the model is unreachable, the LLMError handler in p2/views/errors.py answers 503.
    """
    return patch_loop.run_patch_loop(req.intent, req.k, req.max_attempts)
