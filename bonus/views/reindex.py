"""POST /bonus/reindex: rebuild the Index now."""
from fastapi import APIRouter

from bonus.services.reindex import reindex_service


class ReindexView:
    def __init__(self, reindex_service):
        # debug: one route, POST /bonus/reindex, with no request body.
        self.reindex_service = reindex_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/reindex", self.reindex, methods=["POST"])

    def reindex(self):
        # debug: POST /bonus/reindex. return == {"chunks": N}, N is the Chunk count after index_all.
        return self.reindex_service.reindex()


reindex_view = ReindexView(reindex_service)
