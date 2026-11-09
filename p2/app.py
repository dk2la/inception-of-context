"""FastAPI routes and the dashboard for Part 2."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from p2 import search
from p2 import ask

app = FastAPI()


@app.get("/status")
def status():
    return {"status": "ok"}


class ContextRequest(BaseModel):
    query: str
    k: int = 5


@app.post("/context")
def context(req: ContextRequest):
    return {"results": search.search(req.query, req.k)}


class AskRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/ask")
def ask_route(req: AskRequest):
    return ask.ask(req.question, req.k)


@app.exception_handler(ask.LLMError)
def model_unreachable(request, error):
    """Any route that needs the model answers 503 with a readable message, not a generic 500."""
    return JSONResponse(status_code=503, content={"detail": str(error)})
