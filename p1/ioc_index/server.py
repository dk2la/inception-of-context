"""HTTP surface of part 1: index state, files, chunks, live events, dashboard shell.

Later parts call `create_app(ctx, routers=[...], tabs=[...])` to add their own
endpoints and dashboard tabs on top of this one.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .app import Context
from .walker import read_text

STATIC = Path(__file__).parent / "static"


@dataclass
class Tab:
    id: str
    title: str
    script: str          # URL of the JS module that registers the tab


P1_TABS = [Tab("overview", "Overview", "/static/p1/overview.js"),
           Tab("files", "Files", "/static/p1/files.js")]


def core_router(ctx: Context, features: list[str]) -> APIRouter:
    r = APIRouter()
    s = ctx.settings

    @r.get("/status")
    def status() -> dict:
        return {
            "version": __version__,
            "state": ctx.indexer.state,
            "chunks": ctx.store.count(),
            "files": len(ctx.store.all_paths()),
            "target": str(s.target),
            "chroma_path": str(s.chroma_path),
            "collection": s.collection,
            "embed_model": ctx.embedder.name,
            "ask_model": s.ask_model,
            "code_model": s.code_model,
            "ollama_url": s.ollama_url,
            "watcher": ctx.watcher.backend,
            "last_sync": ctx.indexer.last_sync,
            "features": features,
        }

    @r.get("/files")
    def files() -> dict:
        items = ctx.indexer.files_overview()
        return {"target": str(s.target), "count": len(items), "files": items}

    @r.get("/file")
    def file(path: str = Query(..., description="target-relative path")) -> dict:
        full = ctx.indexer.safe_path(path)
        if full is None:
            raise HTTPException(400, "path must be a relative path inside the target")
        if not full.is_file():
            raise HTTPException(404, f"no such file: {path}")
        rel = full.relative_to(s.target).as_posix()
        content = read_text(full)
        chunks = sorted(({"id": cid, **{k: m[k] for k in ("start_line", "end_line", "kind", "symbol")}}
                         for cid, m in ctx.store.file_chunks(rel).items()), key=lambda c: c["start_line"])
        return {"path": rel, "content": content, "lines": content.count("\n") + 1,
                "bytes": full.stat().st_size, "chunks": chunks}

    @r.get("/chunks")
    def chunks(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=200),
               path: str | None = None, kind: str | None = None) -> dict:
        clauses = [{"path": path}] if path else []
        if kind:
            clauses.append({"kind": kind})
        where = None if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}
        total, rows = ctx.store.page(offset, limit, where)
        return {"total": total, "offset": offset, "limit": limit, "items": rows}

    @r.get("/events")
    async def events(request: Request, since: int | None = None) -> StreamingResponse:
        """Server-Sent Events: replays recent activity, then streams new events live."""
        async def gen():
            last = since if since is not None else ctx.events.last_seq
            yield "retry: 2000\n\n"
            idle = 0.0
            while not await request.is_disconnected():
                batch = await asyncio.to_thread(ctx.events.wait, last, 1.0)
                for ev in batch:
                    last = ev["seq"]
                    yield f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
                idle = 0.0 if batch else idle + 1.0
                if idle >= 15:
                    idle = 0.0
                    yield ": keep-alive\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @r.get("/events/recent")
    def recent(n: int = Query(50, ge=1, le=500)) -> list[dict]:
        return ctx.events.recent(n)

    return r


def create_app(ctx: Context, routers: list[APIRouter] | None = None, tabs: list[Tab] | None = None,
               static_dirs: dict[str, Path] | None = None, features: list[str] | None = None,
               start: bool = True) -> FastAPI:
    all_tabs = P1_TABS + (tabs or [])
    feats = ["index", "watch"] + (features or [])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start:
            ctx.start(background=True)
        yield
        ctx.stop()

    app = FastAPI(title="Inception-of-Context Architect", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx
    app.include_router(core_router(ctx, feats))
    for router in routers or []:
        app.include_router(router)
    app.mount("/static/p1", StaticFiles(directory=STATIC), name="static-p1")
    for name, directory in (static_dirs or {}).items():
        app.mount(f"/static/{name}", StaticFiles(directory=directory), name=f"static-{name}")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        html = (STATIC / "index.html").read_text()
        tags = "\n".join(f'<script src="{t.script}"></script>' for t in all_tabs)
        order = json.dumps([{"id": t.id, "title": t.title} for t in all_tabs])
        return html.replace("<!--IOC_TABS-->", f"<script>window.IOC_TAB_ORDER={order};</script>\n{tags}")

    return app
