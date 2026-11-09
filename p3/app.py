"""Part 3 extends the Part 2 app: it is the same app, with the Patch route added."""
from fastapi import HTTPException
from pydantic import BaseModel

from p2 import ask
from p2.app import app
from p3 import loop


class PatchRequest(BaseModel):
    intent: str
    k: int = 5
    max_attempts: int = 3


@app.post("/patch")
def patch(req: PatchRequest):
    """Run the Patch Loop. A plain def (not async def), so the server answers other requests meanwhile."""
    try:
        return loop.run_patch_loop(req.intent, req.k, req.max_attempts)
    except ask.LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))
