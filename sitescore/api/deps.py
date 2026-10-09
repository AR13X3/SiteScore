"""Shared objects for request handlers."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

from sitescore.config import load_business_type, load_model_config, load_region
from sitescore.datastore import DataStore
from sitescore.model.market import Market, build_market
from sitescore.settings import get_settings


@lru_cache
def get_store() -> DataStore:
    return DataStore(force_mock=get_settings().force_mock)


def get_market(store: DataStore, as_of: dt.date, type_id: str) -> Market:
    """Market for (date, business type), cached until the data on disk changes."""
    catalog = store.root / "catalog.json"
    data_version = catalog.stat().st_mtime if catalog.exists() else 0.0
    return _cached_market(store, as_of, type_id, data_version)


@lru_cache(maxsize=32)
def _cached_market(store: DataStore, as_of: dt.date, type_id: str, data_version: float) -> Market:
    return build_market(store.as_of(as_of), load_business_type(type_id), load_model_config(),
                        load_region())
