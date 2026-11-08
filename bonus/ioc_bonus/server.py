"""Bonus HTTP surface layered on top of part 3."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from ioc_api.llm import LLMError
from ioc_index.app import Context
from ioc_index.server import Tab
from ioc_patch.loop import PatchLoop
from ioc_patch.sanity import check_patch
from ioc_patch.schema import parse_patch
from ioc_patch.server import attach_patch_services, create_app as create_p3_app

from . import gitops
from .diffs import patch_diff

STATIC = Path(__file__).parent / "static"
BONUS_TABS = [Tab("bonus", "Diff & Git", "/static/bonus/bonus.js")]


class BonusPatchLoop(PatchLoop):
    """Same loop; additionally records a visual diff of the committed patch and can git-commit it."""

    autocommit = os.environ.get("IOC_AUTOCOMMIT", "0").lower() in ("1", "true", "yes", "on")

    def run(self, intent, k=5, max_attempts=3, emit=None):
        target = self.ctx.settings.target
        baseline = {}
        for rel in self.ctx.indexer.filter.walk():
            try:
                baseline[rel] = (target / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        result = super().run(intent, k, max_attempts, emit=None if emit is None else emit_filter(emit))
        if result["status"] == "success" and result["patch"]:
            patch = parse_patch(result["patch"])
            result["diff"] = patch_diff(patch, target, {p: baseline.get(p) for p in patch.paths})
            if self.autocommit:
                msg = gitops.commit_message(self.ctx.extras["llm"], self.ctx.settings.ask_model, patch.summary, patch.paths)
                result["git"] = gitops.commit(target, patch.paths, msg)
                self.ctx.events.publish("git", **{k: v for k, v in result["git"].items() if k != "skipped"})
        if emit:
            emit({"event": "done", "result": result})
        return result


def emit_filter(emit):
    """Hold back the parent's `done` event: the bonus loop emits its own, enriched one."""
    def inner(ev):
        if ev.get("event") != "done":
            emit(ev)
    return inner


class DryRunRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=4000)
    k: int = Field(5, ge=1, le=50)


def bonus_router(ctx: Context) -> APIRouter:
    r = APIRouter()

    @r.post("/reindex")
    def reindex(reset: bool = False) -> dict:
        """On-demand full reindex (useful if the watcher ever misses an event)."""
        with ctx.indexer.lock:
            if reset:
                ctx.store.reset()
                ctx.indexer._file_hashes.clear()
            stats = ctx.indexer.full_sync(quiet=True)
        ctx.events.publish("reindex", reset=reset, **stats)
        return {"reset": reset, **stats}

    @r.post("/patch/dry-run")
    def dry_run(req: DryRunRequest) -> dict:
        """Generate + sanity-check a patch and return its diff. The disk is never touched."""
        loop = ctx.extras["patch_loop"]
        try:
            raw, patch, fmt_error, info = loop.generator.generate(req.intent, req.k)
        except LLMError as exc:
            raise HTTPException(503, f"local LLM unavailable: {exc}")
        if patch is None:
            return {"ok": False, "stage": "generate", "error": fmt_error, "raw": raw[:4000], **info}
        violations = check_patch(patch, ctx.settings.target, ctx.indexer.filter)
        return {"ok": not violations, "patch": patch.to_dict(), "violations": violations,
                "diff": patch_diff(patch, ctx.settings.target), **info}

    @r.get("/git")
    def git_state() -> dict:
        target = ctx.settings.target
        return {"repo": gitops.is_repo(target), "autocommit": BonusPatchLoop.autocommit, "log": gitops.log(target)}

    return r


def create_app(ctx: Context, start: bool = True) -> FastAPI:
    if "ask" not in ctx.extras:
        attach_patch_services(ctx)
    if not isinstance(ctx.extras.get("patch_loop"), BonusPatchLoop):
        ctx.extras["patch_loop"] = BonusPatchLoop(ctx)
    return create_p3_app(ctx, routers=[bonus_router(ctx)], tabs=BONUS_TABS, static_dirs={"bonus": STATIC},
                         features=["reindex", "dry-run", "git"], start=start)
