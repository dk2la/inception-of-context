"""GET /bonus/bonus.js: the dashboard additions. Served only by bonus.app."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")


class BonusStaticView:
    def __init__(self, static_dir):
        # debug: static_dir is bonus/static. One route, GET /bonus/bonus.js.
        self.static_dir = static_dir
        self.router = APIRouter()
        self.router.add_api_route("/bonus/bonus.js", self.script, methods=["GET"])

    def script(self):
        # debug: GET /bonus/bonus.js. The body is bonus/static/bonus.js, media_type "text/javascript".
        return FileResponse(os.path.join(self.static_dir, "bonus.js"), media_type="text/javascript")


bonus_static_view = BonusStaticView(STATIC_DIR)
