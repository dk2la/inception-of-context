"""Routes for Questions: retrieval only (/context) and answers (/ask)."""
from fastapi import APIRouter

from p2.schemas.requests import AskRequest, ContextRequest
from p2.schemas.responses import AskResponse, ContextResponse
from p2.services.ask import ask_service
from p2.services.search import search_service


class QuestionsView:
    def __init__(self, search_service, ask_service):
        self.search_service = search_service
        self.ask_service = ask_service
        self.router = APIRouter()
        self.router.add_api_route("/context", self.context, methods=["POST"], response_model=ContextResponse)
        self.router.add_api_route("/ask", self.ask, methods=["POST"], response_model=AskResponse,
                                  response_model_exclude_unset=True)

    def context(self, req: ContextRequest):
        return {"results": self.search_service.search(req.query, req.k)}

    def ask(self, req: AskRequest):
        return self.ask_service.ask(req.question, req.k)


questions_view = QuestionsView(search_service, ask_service)
