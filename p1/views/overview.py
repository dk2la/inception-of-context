"""Routes that show the Index: status, files, one file, pages of Chunks."""
from fastapi import APIRouter, HTTPException, Query

from p1.schemas.responses import ChunkPage, FileCount, FileView, Status
from p1.services.overview import overview_service


class OverviewView:
    def __init__(self, overview_service):
        self.overview_service = overview_service
        self.router = APIRouter()
        self.router.add_api_route("/status", self.status, methods=["GET"], response_model=Status)
        self.router.add_api_route("/files", self.files, methods=["GET"], response_model=list[FileCount])
        self.router.add_api_route("/file", self.get_file, methods=["GET"], response_model=FileView)
        self.router.add_api_route("/chunks", self.chunks, methods=["GET"], response_model=ChunkPage)

    def status(self):
        return self.overview_service.status()

    def files(self):
        return self.overview_service.files()

    def get_file(self, path: str):
        found = self.overview_service.file_with_chunks(path)
        if found is None:
            raise HTTPException(status_code=404, detail="file not found")
        return found

    def chunks(self, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        return self.overview_service.chunks_page(offset, limit)


overview_view = OverviewView(overview_service)
