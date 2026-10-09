"""FastAPI app. Serves the JSON API under /api and the built frontend at /."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from sitescore import __version__
from sitescore.api import routes_meta
from sitescore.api.deps import get_store
from sitescore.config import load_business_types, load_model_config, load_region
from sitescore.paths import FRONTEND_DIST
from sitescore.pipeline import ensure_tables

log = logging.getLogger("sitescore")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Validate all config up front so a bad YAML edit fails immediately.
    load_model_config()
    load_business_types()
    load_region()
    # First run with no data yet: generate mock tables so the demo always works.
    for r in ensure_tables(get_store()):
        log.warning("No data for '%s'; generated mock (%d rows)", r.table, r.rows)
    yield


app = FastAPI(title="SiteScore", version=__version__, lifespan=lifespan)
app.include_router(routes_meta.router)

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def placeholder() -> str:
        return (
            "<h1>SiteScore API is running</h1>"
            "<p>Frontend not built yet. API docs: <a href='/docs'>/docs</a></p>"
        )
