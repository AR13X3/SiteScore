"""Shared objects for request handlers."""

from __future__ import annotations

from functools import lru_cache

from sitescore.datastore import DataStore
from sitescore.settings import get_settings


@lru_cache
def get_store() -> DataStore:
    return DataStore(force_mock=get_settings().force_mock)
