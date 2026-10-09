"""Read-only endpoints describing configuration: region, business types, data sources."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends

from sitescore import __version__
from sitescore.api.deps import get_store
from sitescore.backtest.cohort import data_ready_date
from sitescore.config import load_business_types, load_region, load_sources
from sitescore.datastore import TABLES, DataStore
from sitescore.pipeline.geocode import search as address_search
from sitescore.settings import get_settings

router = APIRouter(prefix="/api", tags=["meta"])
StoreDep = Annotated[DataStore, Depends(get_store)]


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "region": get_settings().region}


@router.get("/region")
def region() -> dict:
    return load_region().model_dump()


@router.get("/business-types")
def business_types() -> list[dict]:
    return [
        {"id": p.id, "name": p.name, "description": p.description, "status": p.status}
        for p in load_business_types().values()
    ]


@router.get("/business-types/{type_id}")
def business_type(type_id: str) -> dict:
    return load_business_types()[type_id].model_dump()


@router.get("/sources")
def sources() -> list[dict]:
    settings = get_settings()
    out = []
    for key, src in load_sources().items():
        has_key = bool(getattr(settings, src.env_key.lower(), None)) if src.env_key else None
        out.append({
            "id": key,
            "title": src.title,
            "provider": src.provider,
            "licence": src.licence,
            "used_for": src.used_for,
            "needs_key": src.needs_key,
            "key_configured": has_key,
        })
    return out


@router.get("/geocode")
def geocode(q: str) -> list[dict]:
    """Address search within the region (NSW Spatial Services, fallback Nominatim)."""
    if get_settings().offline:
        return []
    return list(address_search(q[:200]))


@router.get("/data/as-of-range")
def as_of_range(store: StoreDep) -> dict:
    """Dates the model can run "as of": from the first day every input had been published."""
    return {"min": data_ready_date(store), "max": dt.date.today()}  # noqa: DTZ011


@router.get("/data/status")
def data_status(store: StoreDep) -> list[dict]:
    """Per table: real or mock, row count, publication range, and why if mock."""
    catalog = store.catalog()
    sources = load_sources()
    out = []
    for name, spec in TABLES.items():
        prov = store.provenance(name)
        entry = catalog.get(name, {}).get(prov or "", {})
        out.append({
            "table": name,
            "source": sources[spec.source].title,
            "description": spec.description,
            "provenance": prov,
            "rows": entry.get("rows"),
            "published_range": entry.get("published_range"),
            "note": entry.get("note", ""),
            "model_visible": spec.model_visible,
        })
    return out
