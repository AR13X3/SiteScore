"""Backtesting: predict real openings with data from before they opened, compare with reality."""

from __future__ import annotations

import datetime as dt

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


def load_cohort(name: str, store: DataStore, business_type: str = "cafe") -> list[Business]:
    profile, bt = load_business_type(business_type), load_backtest_config()
    if name == OSM_COHORT:
        return discover_from_osm(store, profile, bt)
    path = COHORT_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"no cohort '{name}' (expected {path})")
    return link_osm_ids(load_csv(path, data_ready_date(store)), store)


def backtest(cohort: str, store: DataStore, business_type: str = "cafe",
             today: dt.date | None = None, limit: int | None = None) -> BacktestResult:
    businesses = load_cohort(cohort, store, business_type)
    if limit:
        businesses = businesses[:limit]
    region = load_region()
    return run_backtest(businesses, cohort, store, load_business_type(business_type),
                        load_model_config(), region, load_calendar(region.state),
                        load_backtest_config(), today or dt.date.today())  # noqa: DTZ011


__all__ = ["OSM_COHORT", "BacktestResult", "Business", "backtest", "load_cohort"]
