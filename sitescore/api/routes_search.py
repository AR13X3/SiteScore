"""Spot finder: the best places for a business inside a circle the user draws."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Annotated, Literal

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
from sitescore.model.search import (
    Area,
    Candidate,
    find_spots,
    grid_candidates,
    in_area,
    nearest_label,
)

router = APIRouter(prefix="/api", tags=["search"])
StoreDep = Annotated[DataStore, Depends(get_store)]


class SearchRequest(BaseModel):
    business_type: str = "cafe"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(1000, gt=50, description="Search radius around (lat, lon)")
    where: Literal["vacant", "anywhere"] = Field(
        "anywhere", description="Vacant shopfronts only, or a grid over the whole circle")
    retail_only: bool = Field(
        True, description="Grid: only near where similar businesses already trade")
    rank_by: Literal["revenue", "profit"] = "revenue"
    as_of: dt.date | None = None
    costs: Costs | None = None


class SpotOut(BaseModel):
    id: str
    label: str
    kind: str
    former_use: str
    lat: float
    lon: float
    rank: int
    total_revenue: float
    total_profit: float | None
    mature_monthly: float
    revenue_range: tuple[float, float] | None   # 36-month P10, P90
    profit_range: tuple[float, float] | None
    prob_loss: float | None
    prob_best: float | None
    headline: str
    quick_monthly: float            # quick-score monthly revenue, or profit when ranked by it
    rent_monthly: float | None      # estimated rent at this spot


class GridPoint(BaseModel):
    lat: float
    lon: float
    quick_monthly: float


class VacancyOut(BaseModel):
    id: str
    lat: float
    lon: float
    label: str
    kind: str
    former_use: str


class SearchResult(BaseModel):
    where: str
    rank_by: str
    as_of: dt.date
    open_date: dt.date | None
    lat: float
    lon: float
    radius_m: float
    n_candidates: int
    n_shortlisted: int
    spots: list[SpotOut]
    grid: list[GridPoint]
    vacancies: list[VacancyOut]
    notes: list[str]


@router.post("/search", response_model=SearchResult)
def search(req: SearchRequest, store: StoreDep) -> SearchResult:
    """Score every candidate in the circle, re-run the best with the full model, rank them."""
    profiles = load_business_types()
    if req.business_type not in profiles:
        raise HTTPException(404, f"unknown business type {req.business_type!r}")
    limit = load_model_config().search.max_radius_m
    if req.radius_m > limit:
        raise HTTPException(422, f"radius is limited to {limit:.0f} m")
    catalog = store.root / "catalog.json"
    version = catalog.stat().st_mtime if catalog.exists() else 0.0
    costs = tuple(req.costs.model_dump().values()) if req.costs else None
    try:
        return _cached(store, req.business_type, round(req.lat, 5), round(req.lon, 5),
                       round(req.radius_m), req.where, req.retail_only, req.rank_by,
                       req.as_of or dt.date.today(), costs, version)  # noqa: DTZ011
    except NoDataAsOf as exc:
        raise HTTPException(422, str(exc)) from exc


@lru_cache(maxsize=32)
def _cached(store: DataStore, business_type: str, lat: float, lon: float, radius_m: float,
            where: str, retail_only: bool, rank_by: str, as_of: dt.date,
            costs: tuple | None, data_version: float) -> SearchResult:
    profile = load_business_types()[business_type]
    if costs is not None:
        profile = profile.model_copy(update={"costs": Costs(**dict(zip(Costs.model_fields, costs, strict=True)))})
    cfg, region = load_model_config(), load_region()
    market = get_market(store, as_of, business_type)
    area = Area(lat, lon, radius_m)
    notes = []

    vacancies = _vacancies(store, as_of, area, market)
    if where == "vacant":
        candidates = vacancies
        if not vacancies:
            notes.append("No vacant shopfronts are mapped in this circle"
                         + ("" if _has_vacancy_data(store, as_of) else
                            f" (vacancy data only exists from its fetch date, after {as_of})")
                         + ". Try a bigger circle or search anywhere.")
        notes.append("Vacant shopfronts come from OpenStreetMap mappers: check each one is still "
                     "available before relying on it.")
    else:
        candidates = grid_candidates(area, market, region, cfg, retail_only)
        if not candidates:
            notes.append("No grid points in this circle are near similar businesses. Turn off "
                         "'only shopping strips' or move the circle.")
        notes.append("Every grid point gets a quick score (agents and the price game off); the "
                     f"best {cfg.search.shortlist}, at least {cfg.search.min_separation_m:.0f} m "
                     "apart, are re-run with the full model.")
    if rank_by == "profit":
        notes.append("Ranked by profit, with each spot's estimated rent (from foot traffic and "
                     "local rents): a busy corner with a high rent can rank below a cheaper one.")

    found = find_spots(market, candidates, profile, cfg, region, load_calendar(region.state),
                       rank_by,  # type: ignore[arg-type]
                       min_separation_m=0 if where == "vacant" else None)
    quick = dict(zip((c.id for c in found.candidates), found.quick, strict=True))
    spots = []
    if found.top is not None:
        odds = {u.site_id: u for u in (found.top.uncertainty.sites if found.top.uncertainty else [])}
        heads = {e.site_id: e.headline for e in found.top.explanations}
        sims = {s.site.id: s for s in found.top.sites}

        def value(site_id: str) -> float:
            s = sims[site_id]
            return s.total_profit if rank_by == "profit" and s.total_profit is not None else s.total_revenue

        ranked = sorted(sims, key=value, reverse=True)[: cfg.search.results]
        for rank, site_id in enumerate(ranked, start=1):
            s, c, u = sims[site_id], found.labels[site_id], odds.get(site_id)
            spots.append(SpotOut(
                id=c.id, label=c.label, kind=c.kind, former_use=c.former_use, lat=c.lat, lon=c.lon,
                rank=rank, total_revenue=s.total_revenue, total_profit=s.total_profit,
                mature_monthly=s.mature.monthly_revenue,
                revenue_range=(u.total_revenue["p10"], u.total_revenue["p90"]) if u else None,
                profit_range=((u.total_profit["p10"], u.total_profit["p90"])
                              if u and u.total_profit else None),
                prob_loss=u.prob_loss if u else None, prob_best=u.prob_best if u else None,
                headline=heads.get(site_id, ""), quick_monthly=float(quick.get(site_id, 0.0)),
                rent_monthly=s.mature.rent.monthly if s.mature.rent else None,
            ))
    grid = [GridPoint(lat=c.lat, lon=c.lon, quick_monthly=float(q))
            for c, q in zip(found.candidates, found.quick, strict=True)] if where == "anywhere" else []
    return SearchResult(
        where=where, rank_by=rank_by, as_of=as_of,
        open_date=found.top.open_date if found.top else None, lat=lat, lon=lon, radius_m=radius_m,
        n_candidates=len(candidates), n_shortlisted=len(found.shortlisted), spots=spots, grid=grid,
        vacancies=[VacancyOut(id=v.id, lat=v.lat, lon=v.lon, label=v.label, kind=v.kind,
                              former_use=v.former_use) for v in vacancies],
        notes=notes,
    )


def _vacancies(store: DataStore, as_of: dt.date, area: Area, market) -> list[Candidate]:
    """Vacant shopfronts in the circle known on the as-of date (via the as-of view)."""
    try:
        df = store.as_of(as_of).table("vacancies")
    except NoDataAsOf:
        return []
    df = df[in_area(area, df["lat"].to_numpy(float), df["lon"].to_numpy(float))]
    return [Candidate(id=r.osm_id, lat=float(r.lat), lon=float(r.lon),
                      label=r.name or nearest_label(market, r.lat, r.lon), kind=r.kind,
                      former_use=r.former_use or "")
            for r in df.itertuples()]


def _has_vacancy_data(store: DataStore, as_of: dt.date) -> bool:
    try:
        store.as_of(as_of).table("vacancies")
        return True
    except NoDataAsOf:
        return False
