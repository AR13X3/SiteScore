"""FastAPI app. Serves the JSON API under /api and the built frontend at /."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from sitescore import __version__
from sitescore.api import routes_meta
from sitescore.config import load_business_types, load_model_config, load_region
from sitescore.paths import FRONTEND_DIST

app = FastAPI(title="SiteScore", version=__version__)
app.include_router(routes_meta.router)

# Validate all config at startup so a bad YAML edit fails immediately.
load_model_config()
load_business_types()
load_region()

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def placeholder() -> str:
        return (
            "<h1>SiteScore API is running</h1>"
            "<p>Frontend not built yet. API docs: <a href='/docs'>/docs</a></p>"
        )
