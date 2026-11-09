"""FastAPI routes and the dashboard for Part 2."""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/status")
def status():
    return {"status": "ok"}


@app.get("/")
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
