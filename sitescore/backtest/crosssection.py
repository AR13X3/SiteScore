"""Cross-section: score every independent café open today with today's data.

NOT time-safe, and labelled so everywhere. The backtest asks "could we have
known before it opened?"; this asks the weaker question "do today's model scores
line up with how today's cafés are doing?". It's useful because it's ~6x the
sample of genuine new openings, but the inputs and the outcomes are entangled:
today's map already reflects which cafés succeeded (rivals open near busy spots,
weak ones have closed), and each café has shaped its own surroundings.

Each café is scored against today's market with itself removed from the
competitor set. Outcomes, when available:
- Google reviews per month (review count / months since the café was first known
  anywhere: OSM first mapped or Foursquare added, clamped to 6-120 months);
- Google review count (log), a popularity stock that needs no age guess;
- site churn: other cafés that closed at the same spot since 2019 (fewer is better).

The layer ladder shows which model layers add ranking power over foot traffic only.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from sitescore.backtest import lifecycle, metrics
from sitescore.backtest.cohort import Business
from sitescore.backtest.outcomes import OutcomeTables, find_place
from sitescore.backtest.types import (
    CrossSectionResult,
    CrossSectionRow,
    OutcomeComparison,
)
from sitescore.config import BacktestCfg, BusinessProfile, ModelConfig, Region
from sitescore.datastore import TABLES, DataStore
from sitescore.matching import best_match
from sitescore.model.market import build_market
from sitescore.model.site import analyse_site
from sitescore.model.types import Site

CAVEATS = [
    ("Not time-safe: cafés are scored with today's data and compared with today's "
     "outcomes. Today's map already reflects which cafés succeeded (rivals cluster near "
     "busy spots, weak cafés have closed), so this shows association, not prediction. "
     "The backtest is the time-safe test."),
    ("Survivors only: cafés that already closed aren't in today's population, which "
     "narrows the spread of outcomes."),
    ("Reviews per month divides by the time since the café was first known anywhere "
     "(first mapped or added to Foursquare), clamped to 6-120 months; that understates "
     "the age of old cafés. The plain review count needs no age guess but favours them."),
    ("Site churn counts other cafés that closed within 25 m since 2019. Most spots have "
     "none, so it mostly separates 'some turnover' from 'none'."),
    ("Cafés Google lists as permanently closed (still on the map because nobody has "
     "updated it) are left out of the review outcomes, since their reviews stopped when "
     "they closed; they are compared instead in 'still trading per Google'."),
]

OUTCOMES = {
    "reviews_per_month": "Google reviews per month",
    "log_reviews": "Google review count (log)",
    "google_open": "Still trading per Google (vs permanently closed)",
    "site_churn": "Fewer café closures at the spot since 2019",
}


def population(lc: pd.DataFrame, store: DataStore, include_chains: bool) -> pd.DataFrame:
    """Businesses of this type on today's map: open runs, named, independent by default."""
    pois = store.read("pois")
    today_ids = set(pois.loc[pois["version"] == pois["version"].max(), "osm_id"])
    pop = lc[lc["closed"].isna() & (lc["continued_as"] == "") & (lc["name"] != "")
             & lc["osm_id"].isin(today_ids)]
    if not include_chains:
        pop = pop[pop["brand"] == ""]
    return pop.reset_index(drop=True)


def cross_section(store: DataStore, profile: BusinessProfile, cfg: ModelConfig, region: Region,
                  bt: BacktestCfg, today: dt.date, lifecycles: pd.DataFrame | None = None
                  ) -> CrossSectionResult:
    lc = lifecycle.build(store, profile, bt.survival) if lifecycles is None else lifecycles
    pop = population(lc, store, bt.include_chains)
    market = build_market(store.as_of(today), profile, cfg, region)

    layers, monthly, profits, rents = [], [], [], []
    for r in pop.itertuples():
        site = Site(id=r.osm_id, label=r.name, lat=r.lat, lon=r.lon)
        result = analyse_site(market.without({r.osm_id}), site, profile, cfg, region).result
        layers.append({layer.key: layer.factor for layer in result.layers})
        monthly.append(result.monthly_revenue)
        profits.append(result.monthly_profit)
        rents.append(result.rent.monthly if result.rent else None)

    src = OutcomeTables.load(store)
    rows_data = [_outcomes(r, lc, src, today, bt.survival.site_radius_m)
                 for r in pop.itertuples()]
    scores = metrics.ladder_scores(
        layers, np.array(profits, float) if all(p is not None for p in profits) else None)
    ranks = 1 + np.argsort(np.argsort(-scores["full"], kind="stable"))
    rows = [CrossSectionRow(
        name=r.name, osm_id=r.osm_id, lat=r.lat, lon=r.lon,
        first_mapped=r.opened.date() if pd.notna(r.opened) else None,
        predicted_rank=int(ranks[i]), mature_monthly=monthly[i], layers=layers[i],
        mature_profit=profits[i], rent_monthly=rents[i],
        **rows_data[i],
    ) for i, r in enumerate(pop.itertuples())]

    outcomes = [OutcomeComparison(**metrics.compare_outcome(
        key, label, scores, outcome_values(key, rows, src.places is not None),
        "needs Google Places (GOOGLE_PLACES_API_KEY)"))
        for key, label in OUTCOMES.items()]
    return CrossSectionResult(
        business_type=profile.id, run_on=today, as_of=market.as_of, n=len(rows), rows=rows,
        outcomes=outcomes, provenance={t: store.provenance(t) for t in TABLES},
        caveats=CAVEATS,
    )


def outcome_values(key: str, rows: list[CrossSectionRow], have_google: bool
                   ) -> np.ndarray | None:
    """One outcome per café (higher = better, NaN = unknown), None if unavailable."""
    if key == "site_churn":
        return -np.array([x.site_closures for x in rows], float)
    if not have_google:
        return None
    if key == "google_open":
        return np.array([{"OPERATIONAL": 1.0, "CLOSED_PERMANENTLY": 0.0}.get(
            x.google_status or "", np.nan) for x in rows])
    # Reviews stop when a café closes, so closed ones don't count here.
    open_ = [x.google_status != "CLOSED_PERMANENTLY" for x in rows]
    if key == "log_reviews":
        return np.array([np.log1p(x.reviews) if x.reviews is not None and ok else np.nan
                         for x, ok in zip(rows, open_, strict=True)])
    return np.array([x.reviews_per_month if x.reviews_per_month is not None and ok
                     else np.nan for x, ok in zip(rows, open_, strict=True)])


def _outcomes(r, lc: pd.DataFrame, src: OutcomeTables, today: dt.date, radius_m: float
              ) -> dict:
    """Google reviews (when available), age and site churn for one café."""
    b = Business(r.name, r.lat, r.lon, today, today, osm_id=r.osm_id)
    known = [r.opened] if pd.notna(r.opened) else []
    fsq = best_match(r.name, r.lat, r.lon, src.fsq, max_m=150) if src.fsq is not None else None
    if fsq is not None and pd.notna(fsq["date_created"]):
        known.append(pd.Timestamp(fsq["date_created"]))
    age = (pd.Timestamp(today) - min(known)).days / 30.44 if known else None
    place = find_place(b, src.places)
    reviews = None if place is None else int(place["review_count"])
    spot = lifecycle.site_closures(lc, r.lat, r.lon, radius_m)
    return {
        "reviews": reviews,
        "reviews_per_month": (None if reviews is None or age is None
                              else reviews / float(np.clip(age, 6, 120))),
        "rating": None if place is None else float(place["rating"]),
        "google_status": None if place is None else (place["business_status"] or None),
        "age_months": None if age is None else round(age, 1),
        "site_closures": int((spot["run_id"] != r.run_id).sum()),
    }
