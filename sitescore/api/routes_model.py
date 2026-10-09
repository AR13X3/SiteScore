"""Model endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sitescore.api.deps import get_market, get_store
from sitescore.config import load_business_types, load_model_config, load_region
from sitescore.datastore import DataStore, NoDataAsOf
from sitescore.model.site import evaluate_site
from sitescore.model.types import Site, SiteResult

router = APIRouter(prefix="/api", tags=["model"])
StoreDep = Annotated[DataStore, Depends(get_store)]


class EvaluateRequest(BaseModel):
    business_type: str = "cafe"
    sites: list[Site] = Field(min_length=1, max_length=5)
    as_of: dt.date | None = Field(None, description="Run as of this date (default: today)")


@router.post("/evaluate", response_model=list[SiteResult])
def evaluate(req: EvaluateRequest, store: StoreDep) -> list[SiteResult]:
    """Mature monthly revenue per site, with a per-layer explanation."""
    profiles = load_business_types()
    if req.business_type not in profiles:
        raise HTTPException(404, f"unknown business type {req.business_type!r}")
    as_of = req.as_of or dt.date.today()  # noqa: DTZ011 (local calendar date is intended)
    try:
        market = get_market(store, as_of, req.business_type)
    except NoDataAsOf as exc:
        raise HTTPException(422, str(exc)) from exc
    sites = [s if s.id else s.model_copy(update={"id": f"site-{i + 1}"})
             for i, s in enumerate(req.sites)]
    profile, cfg, region = profiles[req.business_type], load_model_config(), load_region()
    return [evaluate_site(market, s, profile, cfg, region) for s in sites]
