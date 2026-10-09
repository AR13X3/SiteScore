"""Cross-section (today's cafés, today's data) and the layer-by-layer ladder."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from sitescore.backtest import cross_section_report
from sitescore.backtest.metrics import (
    LADDER,
    compare_outcome,
    ladder_comparison,
    ladder_scores,
    pairwise_accuracy,
)
from sitescore.config import load_business_type, load_model_config, load_region
from sitescore.model.market import build_market
from sitescore.model.site import analyse_site
from sitescore.model.types import Site

TODAY = dt.date(2026, 10, 9)
CAFE, CFG, REGION = load_business_type("cafe"), load_model_config(), load_region()


@pytest.fixture(scope="module")
def report(mock_store):
    return cross_section_report(mock_store, "cafe", TODAY)


def test_market_without_matches_building_it_without(mock_store):
    view = mock_store.as_of(TODAY)
    market = build_market(view, CAFE, CFG, REGION)
    osm_id = str(market.competitors.ids[0])
    built = build_market(view, CAFE, CFG, REGION, exclude_osm_ids=(osm_id,))
    cheap = market.without({osm_id})
    assert list(cheap.competitors.ids) == list(built.competitors.ids)
    assert osm_id not in set(cheap.competitors.ids) and osm_id in set(market.competitors.ids)
    site = Site(id="s", label="s", lat=float(market.competitors.lat[0]),
                lon=float(market.competitors.lon[0]))
    a = analyse_site(cheap, site, CAFE, CFG, REGION).result.monthly_revenue
    b = analyse_site(built, site, CAFE, CFG, REGION).result.monthly_revenue
    assert a == pytest.approx(b)


def test_ladder_rungs_are_running_products_ending_at_revenue():
    layers = [{"demand": 1000, "fit": 1.1, "anchors": 1.2, "competition": 0.2, "behaviour": 0.9,
               "price": 0.95, "spend": 60.0},
              {"demand": 500, "fit": 0.9, "anchors": 1.0, "competition": 0.4, "behaviour": 1.1,
               "price": 1.0, "spend": 60.0, "capacity": 0.8}]
    s = ladder_scores(layers)
    assert [k for k, _, _ in LADDER] == list(s)
    assert s["demand"].tolist() == [1000, 500]
    assert s["competition"][0] == pytest.approx(1000 * 1.1 * 1.2 * 0.2)
    assert s["full"][1] == pytest.approx(math.prod(layers[1].values()))


def test_ladder_comparison_and_unavailable_outcomes():
    rng = np.random.default_rng(1)
    demand = rng.uniform(1, 10, 40)
    truth = demand * rng.uniform(0.2, 1.0, 40)        # what the later layers know
    scores = {k: demand for k, _, _ in LADDER} | {"full": truth}
    rows = ladder_comparison(scores, truth + rng.normal(0, 0.1, 40))
    assert rows[0]["gain_ci"] is None and rows[-1]["spearman"] > rows[0]["spearman"]
    assert rows[-1]["gain_ci"][0] > 0                 # a real gain is detected
    assert not compare_outcome("x", "x", scores, None, "needs a key")["available"]
    flat = compare_outcome("x", "x", scores, np.zeros(40), "")
    assert not flat["available"] and "no variation" in flat["note"]


def test_pairwise_accuracy_ignores_tied_outcomes():
    assert pairwise_accuracy([1, 2, 3, 4], [0, 0, 1, 1]) == (1.0, 4)


def test_cross_section_is_labelled_and_complete(report, mock_store):
    assert not report.time_safe and "Not time-safe" in report.caveats[0]
    assert report.n == len(report.rows) > 50
    assert sorted(r.predicted_rank for r in report.rows) == list(range(1, report.n + 1))
    # mock reviews describe the same world as the mock map, so they're compared
    reviews = next(o for o in report.outcomes if o.outcome == "reviews_per_month")
    assert reviews.available and len(reviews.steps) == len(LADDER) + 1  # + profit after rent
    assert reviews.steps[-1].key == "profit"
    # chains are left out by default
    pois = mock_store.read("pois")
    branded = set(pois.loc[pois["tags"].str.contains('"brand"'), "osm_id"])
    assert not branded & {r.osm_id for r in report.rows}


def test_cross_section_recovers_the_mock_worlds_signal(report):
    """The mock world plants success = local demand - nearby rivals + luck, and turns it
    into review counts; today's scores should line up with them (association only)."""
    reviews = next(o for o in report.outcomes if o.outcome == "reviews_per_month")
    full = reviews.steps[-1]
    assert full.spearman > 0.15 and full.spearman_ci[0] > 0
