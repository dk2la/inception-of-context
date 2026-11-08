"""Part 2 HTTP surface: retrieval (/context) and grounded Q&A (/ask) on top of part 1."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from ioc_index.app import Context
from ioc_index.server import Tab, create_app as create_p1_app

from .ask import AskService
from .llm import LLMError, OllamaClient
from .retriever import Retriever
from .symbols import SymbolIndex

STATIC = Path(__file__).parent / "static"
P2_TABS = [Tab("explorer", "ChromaDB Explorer", "/static/p2/explorer.js"),
           Tab("ask", "Ask & Retrieve", "/static/p2/ask.js")]


class ContextRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    k: int = Field(5, ge=1, le=50)
    path: str | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    k: int = Field(5, ge=1, le=50)
    session_id: str | None = Field(None, max_length=64)


def attach_services(ctx: Context, llm=None) -> Context:
    s = ctx.settings
    ctx.extras["llm"] = llm or OllamaClient(s.ollama_url)
    ctx.extras["retriever"] = Retriever(ctx.store, ctx.embedder)
    ctx.extras["symbols"] = SymbolIndex(ctx.store)
    ctx.extras["ask"] = AskService(ctx.extras["retriever"], ctx.extras["symbols"], ctx.extras["llm"], s.ask_model)
    return ctx


def api_router(ctx: Context) -> APIRouter:
    r = APIRouter()
    retriever: Retriever = ctx.extras["retriever"]
    ask_svc: AskService = ctx.extras["ask"]
    symbols: SymbolIndex = ctx.extras["symbols"]

    @r.post("/context")
    def context(req: ContextRequest) -> dict:
        hits = retriever.search(req.query, req.k, path=req.path)
        return {"query": req.query, "k": req.k, "count": len(hits), "chunks": hits}

    @r.post("/ask")
    def ask(req: AskRequest) -> dict:
        try:
            return ask_svc.ask(req.question, req.k, req.session_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except LLMError as exc:
            raise HTTPException(503, f"local LLM unavailable: {exc}")

    @r.delete("/ask/session/{session_id}")
    def reset(session_id: str) -> dict:
        ask_svc.reset(session_id)
        return {"ok": True}

    @r.get("/symbols")
    def list_symbols(path: str | None = None) -> dict:
        syms = symbols.in_file(path) if path else (symbols.refresh() or symbols.symbols)
        return {"count": len(syms), "symbols": [s.to_dict() for s in syms]}

    @r.get("/llm/health")
    def llm_health() -> dict:
        return ctx.extras["llm"].health()

    return r


def create_app(ctx: Context, routers=None, tabs=None, static_dirs=None, features=None, start: bool = True) -> FastAPI:
    if "ask" not in ctx.extras:
        attach_services(ctx)
    return create_p1_app(
        ctx,
        routers=[api_router(ctx)] + (routers or []),
        tabs=P2_TABS + (tabs or []),
        static_dirs={"p2": STATIC, **(static_dirs or {})},
        features=["context", "ask"] + (features or []),
        start=start,
    )
