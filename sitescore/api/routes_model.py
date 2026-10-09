"""Model endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sitescore.api.deps import get_market, get_store
from sitescore.config import (
    Costs,
    load_business_types,
    load_calendar,
    load_model_config,
    load_region,
)
from sitescore.datastore import DataStore, NoDataAsOf
from sitescore.model.simulate import simulate
from sitescore.model.site import evaluate_site
from sitescore.model.types import SimulationResult, Site, SiteResult

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
    profile, cfg, region = profiles[req.business_type], load_model_config(), load_region()
    return [evaluate_site(market, s, profile, cfg, region) for s in _with_ids(req.sites)]


class SimulateRequest(EvaluateRequest):
    open_date: dt.date | None = Field(
        None, description="Opening month (default: the month after as_of)")
    uncertainty: bool = Field(
        False, description="Add Monte Carlo P10/P50/P90 bands and each site's chance of being best")
    costs: Costs | None = Field(
        None, description="Override the business type's running costs (rent, wages...) for profit")


@router.post("/simulate", response_model=SimulationResult)
def simulate_sites(req: SimulateRequest, store: StoreDep) -> SimulationResult:
    """36-month revenue per site with ramp-up, seasonality, developments, and why each wins."""
    profiles = load_business_types()
    if req.business_type not in profiles:
        raise HTTPException(404, f"unknown business type {req.business_type!r}")
    as_of = req.as_of or dt.date.today()  # noqa: DTZ011 (local calendar date is intended)
    if req.open_date and req.open_date < as_of:
        raise HTTPException(422, "open_date must not be before as_of")
    try:
        market = get_market(store, as_of, req.business_type)
    except NoDataAsOf as exc:
        raise HTTPException(422, str(exc)) from exc
    profile = profiles[req.business_type]
    if req.costs is not None:
        profile = profile.model_copy(update={"costs": req.costs})
    region = load_region()
    return simulate(market, _with_ids(req.sites), profile, load_model_config(), region,
                    load_calendar(region.state), req.open_date, uncertainty=req.uncertainty)


def _with_ids(sites: list[Site]) -> list[Site]:
    return [s if s.id else s.model_copy(update={"id": f"site-{i + 1}"})
            for i, s in enumerate(sites)]
