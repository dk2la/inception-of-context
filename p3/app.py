"""Part 3 extends the Part 2 app: it is the same app, with the Patch route added."""
from pydantic import BaseModel

from p2.app import app
from p3 import loop


class PatchRequest(BaseModel):
    intent: str
    k: int = 5
    max_attempts: int = loop.MAX_ATTEMPTS


@app.post("/patch")
def patch(req: PatchRequest):
    """Run the Patch Loop. A plain def (not async def), so the server answers other requests meanwhile.

    If the model is unreachable, the app-wide LLMError handler in p2/app.py answers 503.
    """
    return loop.run_patch_loop(req.intent, req.k, req.max_attempts)
