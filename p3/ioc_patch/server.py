"""Part 3 HTTP surface: drive the patch loop from the dashboard."""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ioc_api.llm import LLMError
from ioc_api.server import attach_services, create_app as create_p2_app
from ioc_index.app import Context
from ioc_index.server import Tab

from .generator import PatchGenerator
from .loop import MAX_ATTEMPTS, LoopBusy, PatchLoop
from .sanity import check_patch

STATIC = Path(__file__).parent / "static"
P3_TABS = [Tab("patch", "Patch Loop", "/static/p3/patch.js")]


class PatchRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=4000)
    k: int = Field(5, ge=1, le=50)
    max_attempts: int = Field(MAX_ATTEMPTS, ge=1, le=MAX_ATTEMPTS)
    stream: bool = False


def attach_patch_services(ctx: Context) -> Context:
    if "ask" not in ctx.extras:
        attach_services(ctx)
    ctx.extras.setdefault("patch_loop", PatchLoop(ctx, PatchGenerator(ctx)))
    return ctx


def patch_router(ctx: Context) -> APIRouter:
    r = APIRouter()
    loop: PatchLoop = ctx.extras["patch_loop"]

    @r.post("/patch/run")
    def run(req: PatchRequest):
        """Full iteration: generate -> sanity -> apply -> validate (x3) -> commit or roll back."""
        if loop.busy:
            raise HTTPException(409, "a patch loop is already running")
        if not req.stream:
            try:
                return loop.run(req.intent, req.k, req.max_attempts)
            except LoopBusy as exc:
                raise HTTPException(409, str(exc))
            except ValueError as exc:
                raise HTTPException(422, str(exc))

        q: queue.Queue = queue.Queue()

        def worker():
            try:
                loop.run(req.intent, req.k, req.max_attempts, emit=q.put)
            except Exception as exc:
                q.put({"event": "error", "error": str(exc)})
            finally:
                q.put(None)
        threading.Thread(target=worker, daemon=True).start()

        def gen():
            while True:
                item = q.get()
                if item is None:
                    return
                yield json.dumps(item) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @r.post("/patch/generate")
    def generate(req: PatchRequest) -> dict:
        """Single stage: ask the coder model for a patch and run the sanity checks. Nothing is written."""
        try:
            raw, patch, fmt_error, info = loop.generator.generate(req.intent, req.k)
        except LLMError as exc:
            raise HTTPException(503, f"local LLM unavailable: {exc}")
        if patch is None:
            return {"ok": False, "stage": "generate", "error": fmt_error, "raw": raw, **info}
        violations = check_patch(patch, ctx.settings.target, ctx.indexer.filter)
        return {"ok": not violations, "stage": "sanity", "patch": patch.to_dict(), "violations": violations, **info}

    @r.get("/patch/history")
    def history() -> dict:
        return {"busy": loop.busy, "runs": list(loop.history)}

    return r


def create_app(ctx: Context, routers=None, tabs=None, static_dirs=None, features=None, start: bool = True) -> FastAPI:
    attach_patch_services(ctx)
    return create_p2_app(ctx, routers=[patch_router(ctx)] + (routers or []), tabs=P3_TABS + (tabs or []),
                         static_dirs={"p3": STATIC, **(static_dirs or {})}, features=["patch"] + (features or []),
                         start=start)
