"""Backtest result types (also the API response)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class EvidenceOut(BaseModel):
    source: str
    open: bool
    weight: float
    detail: str
    as_of: dt.date | None = None


class Actual(BaseModel):
    still_open: bool | None
    status_source: str
    survival_score: float | None    # -1 (every source says closed) .. +1 (every source says open)
    evidence: list[EvidenceOut]
    months_open: float
    reviews_per_month: float | None
    rating: float | None
    hours_change: float | None
    notes: list[str]


class BacktestRow(BaseModel):
    name: str
    osm_id: str
    lat: float
    lon: float
    opened: dt.date
    opened_note: str
    as_of: dt.date               # prediction used only data published by this date
    data_cutoff: dt.date | None  # newest publication date actually used (<= as_of)
    predicted_score: float       # projected revenue over the first score_months
    predicted_rank: int
    mature_monthly: float
    demand_only: float           # naive baseline input
    actual: Actual
    actual_score: float | None
    actual_rank: int | None


class Accuracy(BaseModel):
    n: int
    pairwise_accuracy: float | None       # share of pairs ordered correctly (0.5 = chance)
    pairs: int
    spearman: float | None
    survival_auc: float | None            # does the model rank survivors above closures?
    closures: int
    top_third_actual_percentile: float | None
    bottom_third_actual_percentile: float | None
    baseline_pairwise_accuracy: float | None  # naive: foot traffic only
    baseline_spearman: float | None
    baseline_survival_auc: float | None


class Skipped(BaseModel):
    name: str
    reason: str


class BacktestResult(BaseModel):
    cohort: str
    business_type: str
    run_on: dt.date
    score_months: int
    rows: list[BacktestRow]
    accuracy: Accuracy
    skipped: list[Skipped]
    provenance: dict[str, str | None]
    outcome_sources: list[str]
    caveats: list[str]
