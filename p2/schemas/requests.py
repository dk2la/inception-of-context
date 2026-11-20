"""The JSON bodies Part 2's routes accept. FastAPI checks them and answers 422 if one is wrong."""
from pydantic import BaseModel


class ContextRequest(BaseModel):
    query: str
    k: int = 5


class AskRequest(BaseModel):
    question: str
    k: int = 5
