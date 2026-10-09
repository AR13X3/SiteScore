"""Result types shared by the model layers and the API."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class Site(BaseModel):
    id: str = ""
    label: str = ""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LayerResult(BaseModel):
    """One layer's contribution to revenue.

    Revenue is the product of every layer's `factor`, so comparing factors
    between sites explains exactly why one site out-earns another.
    """

    key: str
    label: str
    factor: float
    unit: str  # how to read the factor: "customers", "x", "share", "$/customer"
    summary: str
    details: dict[str, Any] = {}


class DataUsed(BaseModel):
    table: str
    provenance: str
    rows: int
    version: dt.date | None
    latest_published: dt.date | None


class SiteResult(BaseModel):
    site: Site
    business_type: str
    as_of: dt.date
    monthly_visits: float
    monthly_revenue: float  # mature month, before ramp-up and seasonality
    monthly_profit: float | None
    layers: list[LayerResult]
    data_used: list[DataUsed]
