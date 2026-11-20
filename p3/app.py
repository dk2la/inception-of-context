"""Part 3: the Part 2 app, with the Patch Loop route added. This is what the container runs.

    uvicorn p3.app:app
"""
from p3.views import patch
from p2.app import app

app.include_router(patch.router)
