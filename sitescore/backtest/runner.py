"""Run a backtest: predict every business first (phase 1), then look at outcomes (phase 2)."""

from __future__ import annotations

import datetime as dt
import logging

import numpy as np

from sitescore.backtest import metrics
from sitescore.backtest.cohort import Business
from sitescore.backtest.outcomes import Outcome, observe
from sitescore.backtest.predict import Prediction, predict
from sitescore.backtest.types import Accuracy, Actual, BacktestResult, BacktestRow, Skipped
from sitescore.config import BacktestCfg, BusinessProfile, Calendar, ModelConfig, Region
from sitescore.datastore import TABLES, DataStore, NoDataAsOf

log = logging.getLogger(__name__)

CAVEATS = [
    ("Revenue isn't public, so success is measured with proxies: survival, opening-hours "
     "changes and (with Google Places) reviews per month and rating."),
    ("Opening dates discovered from OpenStreetMap are approximate: a business can be "
     "mapped weeks or months after it opens. Provide a CSV with exact dates to tighten this."),
    ("Businesses that opened and closed between two quarterly snapshots are never seen, "
     "so the cohort slightly over-represents survivors."),
    ("Small cohorts give noisy accuracy figures; treat fewer than ~15 businesses as a "
     "demonstration, not evidence."),
]


def run_backtest(businesses: list[Business], cohort: str, store: DataStore,
                 profile: BusinessProfile, cfg: ModelConfig, region: Region, calendar: Calendar,
                 bt: BacktestCfg, today: dt.date) -> BacktestResult:
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

    # --- Phase 2: what actually happened ----------------------------------------------
    outcomes = observe([p.business for p in predictions], store, today)
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
        rows.append(BacktestRow(
            name=b.name, osm_id=b.osm_id, lat=b.lat, lon=b.lon, opened=b.opened,
            opened_note=b.opened_note, as_of=b.as_of, data_cutoff=p.data_cutoff,
            predicted_score=p.score, predicted_rank=int(pred_rank[i]),
            mature_monthly=p.mature_monthly, demand_only=p.demand_only,
            actual=Actual(still_open=o.still_open, status_source=o.status_source,
                          months_open=round(o.months_open, 1),
                          reviews_per_month=o.reviews_per_month, rating=o.rating,
                          hours_change=o.hours_change, notes=o.notes),
            actual_score=None if np.isnan(actual_scores[i]) else float(actual_scores[i]),
            actual_rank=None if np.isnan(actual_scores[i]) else int(act_rank[i]),
        ))
    rows.sort(key=lambda r: r.predicted_rank)

    scored = ~np.isnan(actual_scores)
    alive = np.array([outcomes[_key(p.business)].still_open for p in predictions], dtype=object)
    known = np.array([a is not None for a in alive], dtype=bool)
    accuracy = _accuracy(pred[scored], base[scored], actual_scores[scored],
                         pred[known], base[known], alive[known].astype(bool))
    sources = sorted({o.status_source for o in outcomes.values()}
                     | ({"google"} if any(o.reviews is not None for o in outcomes.values()) else set()))
    return BacktestResult(
        cohort=cohort, business_type=profile.id, run_on=today, score_months=bt.score_months,
        rows=rows, accuracy=accuracy, skipped=skipped,
        provenance={t: store.provenance(t) for t in TABLES},
        outcome_sources=sources, caveats=CAVEATS,
    )


def _key(b: Business) -> str:
    return b.osm_id or b.name


def _ranks(values: np.ndarray) -> np.ndarray:
    """1 = best (highest value); ties share the best rank (1, 2, 2, 4)."""
    v = np.asarray(values, float)
    return np.array([1 + int((v > x).sum()) for x in v], dtype=int)


def _actual_scores(outcomes: list[Outcome], weights: dict[str, float]) -> np.ndarray:
    """Weighted mean of standardised proxies; NaN where a business has none."""
    raw = {
        "survival": [None if o.still_open is None else float(o.still_open) for o in outcomes],
        "reviews_per_month": [o.reviews_per_month for o in outcomes],
        "rating": [o.rating for o in outcomes],
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


def _accuracy(pred, base, actual, pred_known, base_known, alive) -> Accuracy:
    pw, pairs = metrics.pairwise_accuracy(pred, actual)
    top, bottom = metrics.thirds(pred, actual)
    return Accuracy(
        n=len(pred), pairwise_accuracy=pw, pairs=pairs, spearman=metrics.spearman(pred, actual),
        survival_auc=metrics.survival_auc(pred_known, alive), closures=int((~alive).sum()),
        top_third_actual_percentile=top, bottom_third_actual_percentile=bottom,
        baseline_pairwise_accuracy=metrics.pairwise_accuracy(base, actual)[0],
        baseline_spearman=metrics.spearman(base, actual),
        baseline_survival_auc=metrics.survival_auc(base_known, alive),
    )
