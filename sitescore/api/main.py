"""FastAPI app. Serves the JSON API under /api and the built frontend at /."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from sitescore import __version__
from sitescore.api import (
    routes_analyst,
    routes_backtest,
    routes_meta,
    routes_model,
    routes_search,
)
from sitescore.api.deps import get_store
from sitescore.config import load_business_types, load_model_config, load_region
from sitescore.paths import FRONTEND_DIST
from sitescore.pipeline import ensure_tables
from sitescore.settings import get_settings

log = logging.getLogger("sitescore")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Validate all config up front so a bad YAML edit fails immediately.
    load_model_config()
    load_business_types()
    load_region()
    # First run with no data yet: load the demo pack (real), then mock for any gaps,
    # so the demo always works.
    store = app.dependency_overrides.get(get_store, get_store)()
    for r in ensure_tables(store):
        if r.provenance == "real":
            log.warning("No data for '%s'; loaded the demo pack (%d real rows)", r.table, r.rows)
        else:
            log.warning("No data for '%s'; generated mock (%d rows)", r.table, r.rows)
    settings = get_settings()
    if settings.warm_heatmap or settings.warm_evidence:
        threading.Thread(target=_warm, args=(store, settings.warm_heatmap, settings.warm_evidence),
                         daemon=True).start()
    yield


def _warm(store, heatmap: bool, evidence: bool) -> None:
    """Fill the slow caches one after the other, so the first visitors don't wait."""
    if heatmap:
        routes_search.warm_heatmap(store)
    if evidence:
        routes_backtest.warm_evidence(store)


app = FastAPI(title="SiteScore", version=__version__, lifespan=lifespan)
# The GitHub Pages site calls this API from another origin; only the listed ones may.
_origins = [o.strip().rstrip("/") for o in get_settings().cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], max_age=600)
app.include_router(routes_meta.router)
app.include_router(routes_model.router)
app.include_router(routes_backtest.router)
app.include_router(routes_search.router)
app.include_router(routes_analyst.router)

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def placeholder() -> str:
        return (
            "<h1>SiteScore API is running</h1>"
            "<p>Frontend not built yet. API docs: <a href='/docs'>/docs</a></p>"
        )
