"""Backtesting: predict real openings with data from before they opened, compare with reality."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from sitescore.backtest import lifecycle
from sitescore.backtest.cohort import (
    COHORT_DIR,
    Business,
    data_ready_date,
    discover_from_osm,
    link_osm_ids,
    load_csv,
)
from sitescore.backtest.runner import run_backtest
from sitescore.backtest.types import BacktestResult
from sitescore.config import (
    load_backtest_config,
    load_business_type,
    load_calendar,
    load_model_config,
    load_region,
)
from sitescore.datastore import DataStore

OSM_COHORT = "osm"  # discover the cohort from OpenStreetMap history


def load_cohort(name: str, store: DataStore, business_type: str = "cafe",
                lifecycles: pd.DataFrame | None = None) -> list[Business]:
    profile, bt = load_business_type(business_type), load_backtest_config()
    if name == OSM_COHORT:
        return discover_from_osm(store, profile, bt, lifecycles)
    path = COHORT_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"no cohort '{name}' (expected {path})")
    return link_osm_ids(load_csv(path, data_ready_date(store)), store)


def backtest(cohort: str, store: DataStore, business_type: str = "cafe",
             today: dt.date | None = None, limit: int | None = None) -> BacktestResult:
    profile, bt = load_business_type(business_type), load_backtest_config()
    lifecycles = lifecycle.build(store, profile, bt.survival)
    businesses = load_cohort(cohort, store, business_type, lifecycles)
    if limit:
        businesses = businesses[:limit]
    region = load_region()
    return run_backtest(businesses, cohort, store, profile, load_model_config(), region,
                        load_calendar(region.state), bt,
                        today or dt.date.today(), lifecycles)  # noqa: DTZ011


__all__ = ["OSM_COHORT", "BacktestResult", "Business", "backtest", "load_cohort"]
