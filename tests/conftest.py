from __future__ import annotations

import datetime as dt

import pytest

from sitescore.datastore import DataStore
from sitescore.pipeline import build_context, run_all

TODAY = dt.date(2026, 10, 9)


@pytest.fixture(scope="session")
def ctx():
    return build_context(today=TODAY)


@pytest.fixture(scope="session")
def mock_store(tmp_path_factory, ctx) -> DataStore:
    """A store filled with the full mock dataset (same as `run.py data --mock`)."""
    store = DataStore(tmp_path_factory.mktemp("mock_store"))
    run_all(store, ctx, mock_only=True)
    return store
