"""FastAPI routes and the dashboard for Part 2."""
from fastapi import FastAPI
from pydantic import BaseModel

from p2 import search

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
