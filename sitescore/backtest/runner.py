"""Run a backtest: predict every business first (phase 1), then look at outcomes (phase 2)."""

from __future__ import annotations

import datetime as dt
import logging
from collections import Counter

import numpy as np
import pandas as pd

from sitescore.backtest import metrics
from sitescore.backtest.cohort import Business
from sitescore.backtest.openings import OpeningCheck, check_openings
from sitescore.backtest.outcomes import Outcome, observe
from sitescore.backtest.predict import Prediction, predict
from sitescore.backtest.types import (
    Accuracy,
    Actual,
    BacktestResult,
    BacktestRow,
    EvidenceOut,
    HorizonOut,
    OutcomeComparison,
    Skipped,
    SurvivalReport,
    ThirdRow,
)
from sitescore.config import BacktestCfg, BusinessProfile, Calendar, ModelConfig, Region
from sitescore.datastore import TABLES, DataStore, NoDataAsOf

log = logging.getLogger(__name__)

CAVEATS = [
    ("Revenue isn't public, so success is measured with proxies: survival (a vote across "
     "OpenStreetMap, Overture, Foursquare, ASIC business names and Google when available), "
     "opening-hours changes and, with Google Places, reviews per month and rating."),
    ("Opening dates come from when a business was first mapped on OpenStreetMap. Many "
     "'first mapped' businesses are older ones being mapped for the first time; those that "
     "Foursquare or ASIC knew long before, or that were already on the map, are excluded. "
     "'Unverified' openings are kept, so some older businesses remain."),
    ("Closures are dated by the map edit that recorded them; the real closure was on or "
     "before that date. A closure nobody mapped is missed, which is why 'survived' needs "
     "confirmation after the horizon and anything weaker counts as unknown."),
    ("Businesses that opened and closed between two quarterly snapshots are never seen, "
     "so the cohort slightly over-represents survivors."),
    ("Small cohorts give noisy accuracy figures; treat fewer than ~15 businesses, or a "
     "handful of closures, as a demonstration, not evidence."),
]


def run_backtest(businesses: list[Business], cohort: str, store: DataStore,
                 profile: BusinessProfile, cfg: ModelConfig, region: Region, calendar: Calendar,
                 bt: BacktestCfg, today: dt.date, lifecycles: pd.DataFrame | None = None
                 ) -> BacktestResult:
    # --- Phase 1: predictions, data as of each opening only ----------------------------
    predictions: list[Prediction] = []
    skipped: list[Skipped] = []
    for b in businesses:
        months_open = (today - b.opened).days / 30.44
        if months_open < bt.min_months_open:
            skipped.append(Skipped(name=b.name, reason=f"open only {months_open:.0f} months"))
            continue
        try:
            predictions.append(predict(b, store, profile, cfg, region, calendar, bt.score_months))
        except NoDataAsOf as exc:
            skipped.append(Skipped(name=b.name, reason=str(exc)))
    predictions = tuple(predictions)  # frozen before any outcome is read

    # --- Phase 2: which openings were real, and what actually happened -----------------
    discovered = [p.business for p in predictions if p.business.source == "osm_first_mapped"]
    checks = (check_openings(discovered, store, lifecycles, bt)
              if discovered and lifecycles is not None else {})
    scored = []
    for p in predictions:
        c = checks.get(_key(p.business))
        if c and c.verdict in bt.opening_check.exclude:
            skipped.append(Skipped(name=p.business.name,
                                   reason=f"not a new opening ({c.verdict}): {c.detail}"))
        else:
            scored.append(p)
    predictions = tuple(scored)

    outcomes = observe([p.business for p in predictions], store, today,
                       bt.survival_evidence.model_dump(), bt.asic_match_window_months,
                       bt.evidence_half_life_months, lifecycles, bt.survival)
    actual_scores = _actual_scores([outcomes[_key(p.business)] for p in predictions],
                                   bt.outcome_weights.model_dump())

    pred = np.array([p.score for p in predictions])
    base = np.array([p.demand_only for p in predictions])
    rows = []
    pred_rank = _ranks(pred)
    act_rank = _ranks(np.nan_to_num(actual_scores, nan=-np.inf)) if len(pred) else []
    for i, p in enumerate(predictions):
        o = outcomes[_key(p.business)]
        b = p.business
        check = checks.get(_key(b), OpeningCheck("", ""))
        rows.append(BacktestRow(
            name=b.name, osm_id=b.osm_id, lat=b.lat, lon=b.lon, opened=b.opened,
            opened_note=b.opened_note, opening_check=check.verdict, opening_detail=check.detail,
            as_of=b.as_of, data_cutoff=p.data_cutoff,
            predicted_score=p.score, predicted_profit=p.profit, predicted_rank=int(pred_rank[i]),
            mature_monthly=p.mature_monthly, demand_only=p.demand_only, layers=p.layers,
            actual=Actual(still_open=o.still_open, status_source=o.status_source,
                          survival_score=o.survival_score,
                          evidence=[EvidenceOut(**e.__dict__) for e in o.evidence],
                          months_open=round(o.months_open, 1),
                          reviews_per_month=o.reviews_per_month, rating=o.rating,
                          hours_change=o.hours_change, notes=o.notes,
                          horizon=HorizonOut(**o.horizon.__dict__) if o.horizon else None),
            actual_score=None if np.isnan(actual_scores[i]) else float(actual_scores[i]),
            actual_rank=None if np.isnan(actual_scores[i]) else int(act_rank[i]),
        ))
    rows.sort(key=lambda r: r.predicted_rank)

    ok = ~np.isnan(actual_scores)
    sources = sorted({e.source for o in outcomes.values() for e in o.evidence}
                     | ({"google"} if any(o.reviews is not None for o in outcomes.values()) else set()))
    return BacktestResult(
        cohort=cohort, business_type=profile.id, run_on=today, score_months=bt.score_months,
        rows=rows, accuracy=_accuracy(pred[ok], base[ok], actual_scores[ok]),
        survival=_survival([outcomes[_key(p.business)] for p in predictions], pred, base,
                           bt.survival.horizon_months),
        ladder=_ladder(predictions, [outcomes[_key(p.business)] for p in predictions],
                       actual_scores),
        opening_checks=dict(Counter(c.verdict for c in checks.values())),
        skipped=skipped, provenance={t: store.provenance(t) for t in TABLES},
        outcome_sources=sources, caveats=CAVEATS,
    )


def _key(b: Business) -> str:
    return b.osm_id or b.name


def _ranks(values: np.ndarray) -> np.ndarray:
    """1 = best (highest value); ties share the best rank (1, 2, 2, 4)."""
    v = np.asarray(values, float)
    return np.array([1 + int((v > x).sum()) for x in v], dtype=int)


def _actual_scores(outcomes: list[Outcome], weights: dict[str, float]) -> np.ndarray:
    """Weighted mean of standardised proxies; NaN where a business has none.

    Survival counts as the vote's verdict (open +1, closed -1), not its margin: the
    margin mostly says how many sources know the business (a café Google didn't
    match scores lower), not how well it trades. Reviews and rating of a café
    Google lists as closed are left out (they stopped when it closed).
    """
    raw = {
        "survival": [None if o.still_open is None else (1.0 if o.still_open else -1.0)
                     for o in outcomes],
        "reviews_per_month": [None if o.google_closed else o.reviews_per_month
                              for o in outcomes],
        "rating": [None if o.google_closed else o.rating for o in outcomes],
        "hours_change": [o.hours_change for o in outcomes],
    }
    total = np.zeros(len(outcomes))
    weight = np.zeros(len(outcomes))
    for name, values in raw.items():
        v = np.array([np.nan if x is None else x for x in values], dtype=float)
        ok = ~np.isnan(v)
        if ok.sum() < 2 or np.nanstd(v) == 0 or weights.get(name, 0) == 0:
            continue
        z = (v - np.nanmean(v)) / np.nanstd(v)
        total[ok] += weights[name] * z[ok]
        weight[ok] += weights[name]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(weight > 0, total / weight, np.nan)


def _accuracy(pred, base, actual) -> Accuracy:
    pw, pairs = metrics.pairwise_accuracy(pred, actual)
    top, bottom = metrics.thirds(pred, actual)
    return Accuracy(
        n=len(pred), pairwise_accuracy=pw, pairs=pairs, spearman=metrics.spearman(pred, actual),
        top_third_actual_percentile=top, bottom_third_actual_percentile=bottom,
        baseline_pairwise_accuracy=metrics.pairwise_accuracy(base, actual)[0],
        baseline_spearman=metrics.spearman(base, actual),
    )


def _ladder(predictions, outcomes: list[Outcome], actual_scores: np.ndarray
            ) -> list[OutcomeComparison]:
    """Which model layers help, outcome by outcome (time-safe: predictions as of opening)."""
    profit = (np.array([p.profit for p in predictions], float)
              if predictions and all(p.profit is not None for p in predictions) else None)
    scores = metrics.ladder_scores([p.layers for p in predictions], profit)
    h = [o.horizon for o in outcomes]
    survived = np.array([{"survived": 1.0, "closed": 0.0}.get(x.status, np.nan) if x else np.nan
                         for x in h])
    churn = np.array([-x.site_closures if x else np.nan for x in h], float)
    # The same Google outcomes as the cross-section, so the two can be compared directly.
    rpm = np.array([np.nan if o.reviews_per_month is None or o.google_closed
                    else o.reviews_per_month for o in outcomes], float)
    log_reviews = np.array([np.nan if o.reviews is None or o.google_closed
                            else np.log1p(o.reviews) for o in outcomes], float)
    few, google = "too few businesses with this outcome", "needs Google Places (GOOGLE_PLACES_API_KEY)"
    has_google = any(o.reviews is not None for o in outcomes)
    candidates = [
        ("actual_score", "Combined actual-performance score", actual_scores, few),
        ("reviews_per_month", "Google reviews per month since opening", rpm,
         few if has_google else google),
        ("log_reviews", "Google review count (log)", log_reviews, few if has_google else google),
        ("survival_18m", "Survived 18 months (vs closed)", survived, few),
        ("site_churn", "Fewer café closures at the spot since 2019", churn, few),
    ]
    return [OutcomeComparison(**metrics.compare_outcome(key, label, scores, y, note))
            for key, label, y, note in candidates]


def _survival(outcomes: list[Outcome], pred: np.ndarray, base: np.ndarray,
              horizon_months: int) -> SurvivalReport:
    h = [o.horizon for o in outcomes]
    status = np.array([x.status if x else "unknown" for x in h], dtype=object)
    failure = np.array([(x.failure or "") if x else "" for x in h], dtype=object)
    churn = np.array([x.site_closures if x else 0 for x in h], dtype=float)
    judged = np.isin(status, ["closed", "survived"])
    alive = status[judged] == "survived"
    kinds = Counter((x.kind or "unknown") for x in h if x and x.status == "closed")
    return SurvivalReport(
        horizon_months=horizon_months,
        status_counts={s: int((status == s).sum())
                       for s in ("closed", "survived", "censored", "unknown")},
        closure_kinds=dict(kinds),
        auc=metrics.survival_auc(pred[judged], alive),
        baseline_auc=metrics.survival_auc(base[judged], alive),
        by_third=[ThirdRow(**r) for r in metrics.closure_by_third(pred, status, failure, churn)],
        baseline_by_third=[ThirdRow(**r)
                           for r in metrics.closure_by_third(base, status, failure, churn)],
        site_churn_auc=metrics.survival_auc(pred, churn == 0),
        baseline_site_churn_auc=metrics.survival_auc(base, churn == 0),
    )
