"""FastAPI routes and the dashboard for Part 2."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/status")
def status():
    return {"status": "ok"}
