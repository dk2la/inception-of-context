"""Routes for Questions: retrieval only (/context) and answers (/ask)."""
from fastapi import APIRouter

from p2.schemas.requests import AskRequest, ContextRequest
from p2.schemas.responses import AskResponse, ContextResponse
from p2.services import ask
from p2.services import search

router = APIRouter()


@router.post("/context", response_model=ContextResponse)
def context(req: ContextRequest):
    return {"results": search.search(req.query, req.k)}


# exclude_unset: a source answered from the Index has no similarity or score, so it does not show them as null
@router.post("/ask", response_model=AskResponse, response_model_exclude_unset=True)
def ask_route(req: AskRequest):
    return ask.ask(req.question, req.k)
