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
    avg_transaction_value: float
    # Mature visits per segment before any capacity cap (time dynamics use these).
    segment_visits: dict[str, float]
    # Share of mature trade in each month since opening, from the agent simulation
    # (None when agents are off: the profile's ramp curve is used instead).
    ramp: list[float] | None = None
    layers: list[LayerResult]
    data_used: list[DataUsed]


class MonthPoint(BaseModel):
    month: dt.date
    revenue: float
    visits: float
    profit: float | None
    development_revenue: float  # part of revenue from residents of new developments


class SiteSimulation(BaseModel):
    site: Site
    mature: SiteResult
    months: list[MonthPoint]
    total_revenue: float
    total_profit: float | None
    dynamics: LayerResult  # factor = total / (horizon x mature monthly revenue)


class Contribution(BaseModel):
    key: str
    label: str
    ratio: float          # this site's factor / the average candidate's factor
    pct_effect: float     # ratio - 1
    dollars: float        # step in a waterfall from the average candidate to this site


class SiteExplanation(BaseModel):
    site_id: str
    rank: int
    total_revenue: float
    vs_average_pct: float
    headline: str
    contributions: list[Contribution]


class SimulationResult(BaseModel):
    business_type: str
    as_of: dt.date
    open_date: dt.date
    horizon_months: int
    baseline_total_revenue: float  # geometric mean of candidates' 36-month totals
    sites: list[SiteSimulation]
    ranking: list[str]  # site ids, best first
    explanations: list[SiteExplanation]
    data_used: list[DataUsed]
