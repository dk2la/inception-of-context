"""Routes that show the Index: status, files, one file, pages of Chunks."""
from fastapi import APIRouter, HTTPException, Query

from p1.schemas.responses import ChunkPage, FileCount, FileView, Status
from p1.services import overview

router = APIRouter()


@router.get("/status", response_model=Status)
def status():
    return overview.status()


@router.get("/files", response_model=list[FileCount])
def files():
    return overview.files()


@router.get("/file", response_model=FileView)
def get_file(path: str):
    found = overview.file_with_chunks(path)
    if found is None:
        raise HTTPException(status_code=404, detail="file not found")
    return found


@router.get("/chunks", response_model=ChunkPage)
def chunks(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    return overview.chunks_page(offset, limit)
