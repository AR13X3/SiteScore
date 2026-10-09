"""Read-only endpoints describing configuration: region, business types, data sources."""

from __future__ import annotations

from fastapi import APIRouter

from sitescore import __version__
from sitescore.config import load_business_types, load_region, load_sources
from sitescore.settings import get_settings

router = APIRouter(prefix="/api", tags=["meta"])


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
