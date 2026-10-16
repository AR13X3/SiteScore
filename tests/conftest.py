from __future__ import annotations

import dataclasses
import datetime as dt
import os

import pytest

# Tests never reach paid APIs: the real keys in .env are blanked (an environment
# variable beats .env). Tests that need a key pass a fake one explicitly.
os.environ["GOOGLE_PLACES_API_KEY"] = ""
os.environ["TFNSW_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
# No background heatmap scoring while the API starts in tests.
os.environ["SITESCORE_WARM_HEATMAP"] = "0"

from sitescore.datastore import DataStore
from sitescore.pipeline import build_context, run_all

TODAY = dt.date(2026, 10, 9)


@pytest.fixture(scope="session")
def ctx(tmp_path_factory):
    # Never the repo's data/raw: that holds the real Google Places ledger.
    return dataclasses.replace(build_context(today=TODAY),
                               repo_raw_dir=tmp_path_factory.mktemp("repo_raw"))


@pytest.fixture(scope="session")
def mock_store(tmp_path_factory, ctx) -> DataStore:
    """A store filled with the full mock dataset (same as `run.py data --mock`)."""
    store = DataStore(tmp_path_factory.mktemp("mock_store"))
    run_all(store, ctx, mock_only=True)
    return store
