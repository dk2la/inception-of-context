"""GET /: the dashboard, one static HTML page with vanilla JS."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class DashboardView:
    def __init__(self, static_dir):
        self.static_dir = static_dir
        self.router = APIRouter()
        self.router.add_api_route("/", self.dashboard, methods=["GET"])

    def dashboard(self):
        return FileResponse(os.path.join(self.static_dir, "index.html"))


dashboard_view = DashboardView(STATIC_DIR)
