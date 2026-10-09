"""Backtest endpoints."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sitescore.api.deps import get_store
from sitescore.backtest import (
    OSM_COHORT,
    BacktestResult,
    CrossSectionResult,
    backtest,
    cross_section_report,
)
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
    return _cached(store, req.cohort, req.business_type, _data_version(store),
                   dt.date.today())  # noqa: DTZ011


@router.get("/cross-section", response_model=CrossSectionResult)
def cross_section(store: StoreDep, business_type: str = "cafe") -> CrossSectionResult:
    """Every business open today scored with today's data. NOT time-safe: association
    between today's scores and today's outcomes, not prediction."""
    if business_type not in load_business_types():
        raise HTTPException(404, f"unknown business type {business_type!r}")
    return _cached_cross_section(store, business_type, _data_version(store),
                                 dt.date.today())  # noqa: DTZ011


def _data_version(store: DataStore) -> float:
    catalog = store.root / "catalog.json"
    return catalog.stat().st_mtime if catalog.exists() else 0.0


@lru_cache(maxsize=4)
def _cached_cross_section(store: DataStore, business_type: str, data_version: float,
                          today: dt.date) -> CrossSectionResult:
    return cross_section_report(store, business_type, today)


@lru_cache(maxsize=16)
def _cached(store: DataStore, cohort: str, business_type: str, data_version: float,
            today: dt.date) -> BacktestResult:
    return backtest(cohort, store, business_type, today=today)
