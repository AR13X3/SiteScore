"""Backtest endpoints."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sitescore.api.deps import get_store
from sitescore.backtest import OSM_COHORT, BacktestResult, backtest
from sitescore.backtest.cohort import list_cohorts
from sitescore.config import load_business_types
from sitescore.datastore import DataStore

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
StoreDep = Annotated[DataStore, Depends(get_store)]


@router.get("/cohorts")
def cohorts() -> list[dict]:
    return ([{"id": OSM_COHORT, "label": "Discovered from OpenStreetMap history"}]
            + [{"id": c, "label": f"{c}.csv"} for c in list_cohorts()])


class BacktestRequest(BaseModel):
    cohort: str = OSM_COHORT
    business_type: str = "cafe"


@router.post("", response_model=BacktestResult)
def run(req: BacktestRequest, store: StoreDep) -> BacktestResult:
    if req.business_type not in load_business_types():
        raise HTTPException(404, f"unknown business type {req.business_type!r}")
    if req.cohort != OSM_COHORT and req.cohort not in list_cohorts():
        raise HTTPException(404, f"unknown cohort {req.cohort!r}")
    catalog = store.root / "catalog.json"
    version = catalog.stat().st_mtime if catalog.exists() else 0.0
    return _cached(store, req.cohort, req.business_type, version, dt.date.today())  # noqa: DTZ011


@lru_cache(maxsize=16)
def _cached(store: DataStore, cohort: str, business_type: str, data_version: float,
            today: dt.date) -> BacktestResult:
    return backtest(cohort, store, business_type, today=today)
