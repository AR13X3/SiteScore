"""Unit tests for each model layer on tiny hand-built markets."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from sitescore.config import load_business_type, load_model_config
from sitescore.features import FEATURES
from sitescore.model.demand import anchor_boost, compute_demand, reach, time_alignment
from sitescore.model.fit import compute_fit
from sitescore.model.huff import compute_competition, huff_probabilities
from sitescore.model.market import Market, PointSet, Venues
from sitescore.model.spend import compute_spend, effective_atv

CFG = load_model_config()
CAFE = load_business_type("cafe")


def points(xy: list[tuple[float, float]], people: list[float]) -> PointSet:
    arr = np.array(xy, dtype=float).reshape(-1, 2)
    return PointSet(np.array([f"p{i}" for i in range(len(arr))]), arr[:, 0], arr[:, 1],
                    np.array(people, dtype=float))


def venues(xy: list[tuple[float, float]], weight: float = 1.0) -> Venues:
    arr = np.array(xy, dtype=float).reshape(-1, 2)
    n = len(arr)
    return Venues(np.array([f"v{i}" for i in range(n)]), np.array([f"Venue {i}" for i in range(n)]),
                  np.zeros(n), np.zeros(n), arr[:, 0], arr[:, 1], np.full(n, weight))


def market(residents=None, workers=None, commuters=None, competitors=None, anchors=None,
           features: pd.DataFrame | None = None) -> Market:
    residents = residents or points([], [])
    if features is None:
        features = pd.DataFrame({f: np.full(len(residents), 0.3) for f in FEATURES})
    return Market(dt.date(2025, 1, 1), "cafe", residents, features,
                  workers or points([], []), commuters or points([], []),
                  competitors or venues([]), anchors or venues([]))


# --- Huff -----------------------------------------------------------------------------


def test_huff_rows_sum_to_one():
    rng = np.random.default_rng(1)
    p_own, p_comp, p_out = huff_probabilities(
        rng.uniform(50, 800, 20), rng.uniform(50, 800, (20, 6)), 1.0, rng.uniform(0.5, 2, 6),
        alpha=1.0, beta=2.0, outside_attr=1.0, outside_dist=350)
    np.testing.assert_allclose(p_own + p_comp.sum(axis=1) + p_out, 1.0)


def test_huff_alone_matches_formula():
    p_own, _, p_out = huff_probabilities(np.array([100.0]), np.zeros((1, 0)), 1.0, np.zeros(0),
                                         alpha=1, beta=2, outside_attr=1, outside_dist=350)
    expected = 100.0 ** -2 / (100.0 ** -2 + 350.0 ** -2)
    assert p_own[0] == pytest.approx(expected)
    assert p_out[0] == pytest.approx(1 - expected)


def test_huff_symmetry_and_distance():
    _, p_comp, _ = huff_probabilities(np.array([200.0]), np.array([[150.0, 150.0]]), 1.0,
                                      np.array([1.0, 1.0]), 1, 2, 1, 350)
    assert p_comp[0, 0] == pytest.approx(p_comp[0, 1])
    near, _, _ = huff_probabilities(np.array([100.0]), np.array([[300.0]]), 1.0, np.array([1.0]),
                                    1, 2, 1, 350)
    far, _, _ = huff_probabilities(np.array([300.0]), np.array([[100.0]]), 1.0, np.array([1.0]),
                                   1, 2, 1, 350)
    assert near[0] > 0.5 > far[0]


def test_higher_beta_makes_customers_more_local():
    args = (np.array([100.0]), np.array([[300.0]]), 1.0, np.array([1.0]))
    low, _, _ = huff_probabilities(*args, 1, 1.0, 1, 350)
    high, _, _ = huff_probabilities(*args, 1, 3.0, 1, 350)
    assert high[0] > low[0]


# --- Demand ---------------------------------------------------------------------------


def test_time_alignment_by_hand():
    tau = time_alignment(CAFE)
    # Workers: 0.75 weekday x (0.50*1.0 + 0.35*1.0 + 0.15*0.7) + 0.25 weekend x 0.15
    assert tau["workers"] == pytest.approx(0.75 * 0.955 + 0.25 * 0.15)
    assert all(0 <= v <= 1 for v in tau.values())


def test_reach_fades_around_walk_limit():
    r = reach(np.array([0, 400, 500, 600, 700.0]), radius=500, fade=0.2)
    np.testing.assert_allclose(r, [1, 1, 0.5, 0, 0])


def test_demand_has_no_jumps_at_the_catchment_edge():
    """Sweeping a site past a big station in 5 m steps never jumps."""
    m = market(commuters=points([(0, 0)], [20_000]))
    xs = np.arange(0, 500, 5.0)
    demand = np.array([compute_demand(x, 0, m, CAFE, CFG).potential_customers for x in xs])
    assert demand[0] > 0 and demand[-1] == 0
    # A hard edge would drop 100% in one step; the fade band (2 x 0.2 x 320 m of
    # walking) spreads it to ~5% per 5 m step.
    assert np.abs(np.diff(demand)).max() < 0.10 * demand.max()


def test_demand_counts_only_reachable_people_and_scales_linearly():
    radius = CAFE.segments["workers"].max_walk_minutes * CFG.distance.walk_speed_kmh * 1000 / 60
    inside = radius * 0.5 / CFG.distance.detour_factor
    outside = radius * 1.5 / CFG.distance.detour_factor
    m = market(workers=points([(inside, 0), (outside, 0)], [1000, 1000]))
    d = compute_demand(0, 0, m, CAFE, CFG)
    tau = time_alignment(CAFE)["workers"]
    assert d.by_segment["workers"]["potential_customers"] == pytest.approx(
        1000 * CAFE.segments["workers"].participation * tau)
    m2 = market(workers=points([(inside, 0), (outside, 0)], [2000, 2000]))
    assert compute_demand(0, 0, m2, CAFE, CFG).potential_customers == pytest.approx(
        2 * d.potential_customers)


def test_anchor_boost_is_capped_and_increasing():
    assert anchor_boost(0, 0, market(), CAFE, CFG)[0] == 1.0
    one = anchor_boost(0, 0, market(anchors=venues([(50, 0)])), CAFE, CFG)[0]
    many = anchor_boost(0, 0, market(anchors=venues([(50, 0)] * 20)), CAFE, CFG)[0]
    far = anchor_boost(0, 0, market(anchors=venues([(5000, 0)])), CAFE, CFG)[0]
    assert 1.0 < one < many < 1.0 + CAFE.anchors.max_boost
    assert far == 1.0


# --- Fit ------------------------------------------------------------------------------


def _fit_market(young_share_near: float) -> Market:
    """Two resident areas: one next to the site, one far away (sets the region average)."""
    feats = pd.DataFrame({f: [0.3, 0.3] for f in FEATURES})
    feats["age_25_34_share"] = [young_share_near, 0.15]
    return market(residents=points([(50, 0), (20_000, 0)], [500, 500]), features=feats)


def test_fit_neutral_when_catchment_is_average():
    m = _fit_market(young_share_near=0.15)
    d = compute_demand(0, 0, m, CAFE, CFG)
    f = compute_fit(d.catchment, m, CAFE)
    assert f.factor == pytest.approx(1.0)


def test_fit_rewards_matching_demographics_and_explains_why():
    m = _fit_market(young_share_near=0.40)
    d = compute_demand(0, 0, m, CAFE, CFG)
    f = compute_fit(d.catchment, m, CAFE)
    _, hi = CAFE.fit.clip
    assert 1.0 < f.residents_multiplier <= hi
    assert f.contributions[0]["feature"] == "age_25_34_share"
    assert sum(c["contribution"] for c in f.contributions) == pytest.approx(f.index, abs=1e-3)


def test_fit_does_not_touch_workers():
    m = market(workers=points([(50, 0)], [1000]))
    d = compute_demand(0, 0, m, CAFE, CFG)
    assert np.all(compute_fit(d.catchment, m, CAFE).point_multiplier == 1.0)


# --- Competition + spend --------------------------------------------------------------


def test_competitor_next_door_takes_share():
    res = points([(100, 0), (0, 100), (-100, 0)], [400, 400, 400])
    alone = market(residents=res)
    crowded = market(residents=res, competitors=venues([(30, 0), (0, -40)]))
    shares = []
    for m in (alone, crowded):
        d = compute_demand(0, 0, m, CAFE, CFG)
        f = compute_fit(d.catchment, m, CAFE)
        shares.append(compute_competition(0, 0, d.catchment, f.point_multiplier, m, CAFE, CFG).factor)
    assert shares[1] < shares[0]


def test_spend_revenue_and_price_effect():
    m = market(workers=points([(50, 0)], [1000]))
    d = compute_demand(0, 0, m, CAFE, CFG)
    ones = np.ones(len(d.catchment.weight))
    s = compute_spend(d.catchment, ones, ones * 0.1, 1.0, CAFE)
    assert s.revenue == pytest.approx(s.visits * s.atv)
    pricier = CAFE.model_copy(update={"pricing": CAFE.pricing.model_copy(
        update={"our_price": CAFE.pricing.reference_price * 1.1})})
    assert effective_atv(pricier) == pytest.approx(CAFE.spend.avg_transaction_value * 1.1)


def test_capacity_cap_binds():
    m = market(workers=points([(50, 0)], [100_000]))
    d = compute_demand(0, 0, m, CAFE, CFG)
    capped = CAFE.model_copy(update={"spend": CAFE.spend.model_copy(
        update={"capacity_visits_per_month": 1000})})
    ones = np.ones(len(d.catchment.weight))
    s = compute_spend(d.catchment, ones, ones * 0.5, 1.0, capped)
    assert s.visits == pytest.approx(1000) and s.capacity_factor < 1
