"""Errors from the layers below, turned into HTTP answers."""
from fastapi.responses import JSONResponse

from p1.core.llm import LLMError


def model_unreachable(request, error):
    """Any route that needs the model answers 503 with a readable message, not a generic 500."""
    return JSONResponse(status_code=503, content={"detail": str(error)})


def add_error_handlers(app):
    app.add_exception_handler(LLMError, model_unreachable)
