"""Data pipeline: one adapter per source, each with a real fetch and a mock fallback."""

from __future__ import annotations

from sitescore.datastore import TABLES, DataStore
from sitescore.pipeline.abs_census import AbsCensus
from sitescore.pipeline.abs_workers import AbsWorkers
from sitescore.pipeline.base import Adapter, PipelineContext, RunResult, build_context, run_adapter
from sitescore.pipeline.google_places import GooglePlaces
from sitescore.pipeline.osm import Osm
from sitescore.pipeline.planning import PlanningDA
from sitescore.pipeline.tfnsw import TfnswStations

ADAPTERS: tuple[Adapter, ...] = (
    AbsCensus(), AbsWorkers(), TfnswStations(), Osm(), PlanningDA(), GooglePlaces(),
)


def run_all(store: DataStore, ctx: PipelineContext | None = None, *, mock_only: bool = False,
            only: set[str] | None = None) -> list[RunResult]:
    ctx = ctx or build_context()
    results = []
    for adapter in ADAPTERS:
        if only and adapter.source_id not in only:
            continue
        results += run_adapter(adapter, store, ctx, mock_only=mock_only)
    return results


def ensure_tables(store: DataStore, ctx: PipelineContext | None = None) -> list[RunResult]:
    """Generate mock data for any table with no data at all, so the app always starts."""
    missing = {t for t in TABLES if not store.has(t)}
    if not missing:
        return []
    ctx = ctx or build_context()
    results = []
    for adapter in ADAPTERS:
        if missing & set(adapter.tables):
            results += run_adapter(adapter, store, ctx, mock_only=True,
                                   reason="no data yet; mock generated at startup")
    return results


__all__ = ["ADAPTERS", "Adapter", "PipelineContext", "RunResult", "build_context",
           "ensure_tables", "run_all"]
