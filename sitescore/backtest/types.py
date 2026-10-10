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


class HorizonOut(BaseModel):
    status: str                      # closed | survived | censored | unknown
    horizon: dt.date
    closed_on: dt.date | None
    kind: str | None                 # replaced | vacant | other_use | removed
    failure: str | None              # operator | site | unknown
    last_seen_trading: dt.date | None
    detail: str
    site_closures: int               # café closures at this spot on the map's record
    site_closures_before: int


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
    horizon: HorizonOut | None = None


class BacktestRow(BaseModel):
    name: str
    osm_id: str
    lat: float
    lon: float
    opened: dt.date
    opened_note: str
    opening_check: str = ""      # new | unverified (older / remapped are excluded)
    opening_detail: str = ""
    as_of: dt.date               # prediction used only data published by this date
    data_cutoff: dt.date | None  # newest publication date actually used (<= as_of)
    predicted_score: float       # projected revenue over the first score_months
    predicted_profit: float | None = None  # ... and profit, with the site's estimated rent
    predicted_rank: int
    mature_monthly: float
    demand_only: float           # naive baseline input
    layers: dict[str, float] = {}
    actual: Actual
    actual_score: float | None
    actual_rank: int | None


class Accuracy(BaseModel):
    """Predicted score vs the combined actual-performance score."""

    n: int
    pairwise_accuracy: float | None       # share of pairs ordered correctly (0.5 = chance)
    pairs: int
    spearman: float | None
    top_third_actual_percentile: float | None
    bottom_third_actual_percentile: float | None
    baseline_pairwise_accuracy: float | None  # naive: foot traffic only
    baseline_spearman: float | None


class ThirdRow(BaseModel):
    third: str                     # top | middle | bottom, by predicted score
    n: int
    judged: int                    # closed or survived at the horizon
    closed: int
    closure_rate: float | None     # closed / judged
    site_failures: int             # became vacant or another use
    operator_failures: int         # another café took over
    mean_site_closures: float | None


class SurvivalReport(BaseModel):
    """Secondary measure: closed within horizon_months of opening?"""

    horizon_months: int
    status_counts: dict[str, int]          # closed / survived / censored / unknown
    closure_kinds: dict[str, int]          # replaced / vacant / other_use / removed / unknown
    auc: float | None                      # survivors predicted above closures?
    baseline_auc: float | None
    by_third: list[ThirdRow]
    baseline_by_third: list[ThirdRow]
    site_churn_auc: float | None           # spots with no café closures predicted above others?
    baseline_site_churn_auc: float | None


class LadderStep(BaseModel):
    """One rung of the model (layers switched on up to here) against one outcome."""

    key: str
    label: str
    n: int
    pairs: int
    pairwise_accuracy: float | None             # pairs ordered like reality (0.5 = chance)
    spearman: float | None
    spearman_ci: tuple[float, float] | None     # 90% bootstrap interval
    gain_ci: tuple[float, float] | None         # Spearman minus foot traffic only, 90% interval


class OutcomeComparison(BaseModel):
    outcome: str
    label: str
    available: bool
    note: str
    steps: list[LadderStep]


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
    survival: SurvivalReport
    ladder: list[OutcomeComparison]        # which layers help, outcome by outcome
    opening_checks: dict[str, int]         # verdict counts over the discovered cohort
    skipped: list[Skipped]
    provenance: dict[str, str | None]
    outcome_sources: list[str]
    caveats: list[str]


# --- Cross-section (today's cafés, today's data: not time-safe) ---------------------------


class CrossSectionRow(BaseModel):
    name: str
    osm_id: str
    lat: float
    lon: float
    first_mapped: dt.date | None
    predicted_rank: int
    mature_monthly: float
    layers: dict[str, float]
    mature_profit: float | None = None  # with the site's estimated rent
    rent_monthly: float | None = None
    reviews: int | None
    reviews_per_month: float | None   # reviews / months since first known (6-120)
    rating: float | None
    age_months: float | None
    site_closures: int                # other cafés that closed at this spot since 2019
    google_status: str | None = None  # OPERATIONAL / CLOSED_PERMANENTLY / CLOSED_TEMPORARILY


class CrossSectionResult(BaseModel):
    business_type: str
    run_on: dt.date
    as_of: dt.date
    time_safe: bool = False
    n: int
    rows: list[CrossSectionRow]
    outcomes: list[OutcomeComparison]
    provenance: dict[str, str | None]
    caveats: list[str]
