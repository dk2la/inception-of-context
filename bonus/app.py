"""The Part 3 app plus the bonus routes. This is what the container runs.

    uvicorn bonus.app:app
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from p2.views.errors import error_handlers
from p3.app import app as mandatory
from bonus.views.docker_watch import docker_watch_view
from bonus.views.events import bonus_events_view
from bonus.views.patch import bonus_patch_view
from bonus.views.reindex import reindex_view
from bonus.views.static_files import bonus_static_view


class BonusApp:
    """A second app that serves every mandatory route, then the bonus ones.

    It does not add routes to the Part 3 app, so `uvicorn p3.app:app` stays the mandatory server.
    """

    def __init__(self, mandatory):
        self.app = FastAPI(title="Inception-of-Context", lifespan=mandatory.router.lifespan_context)
        for route in mandatory.routes:
            self.app.router.routes.append(route)
        error_handlers.add_error_handlers(self.app)
        for view in (reindex_view, bonus_patch_view, bonus_events_view, docker_watch_view, bonus_static_view):
            self.app.include_router(view.router)
        self.app.middleware("http")(self.inject_script)

    async def inject_script(self, request, call_next):
        """The dashboard page gains the bonus script. Other responses are returned as they are."""
        response = await call_next(request)
        if request.url.path != "/":
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if b"</body>" not in body:
            return HTMLResponse(body, status_code=response.status_code)
        html = body.replace(b"</body>", b'<script src="/bonus/bonus.js"></script></body>', 1)
        return HTMLResponse(html, status_code=response.status_code)


app = BonusApp(mandatory).app
