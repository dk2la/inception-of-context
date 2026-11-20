"""GET /: the dashboard, one static HTML page with vanilla JS."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

router = APIRouter()


@router.get("/")
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
