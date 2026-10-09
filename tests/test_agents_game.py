"""Agent-based layer (4) and price game (5)."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from sitescore.config import load_business_type, load_model_config, load_region
from sitescore.model.agents import ChoiceModel, build_agents, build_stores
from sitescore.model.demand import compute_demand
from sitescore.model.dynamics import ramp_curve
from sitescore.model.fit import compute_fit
from sitescore.model.game import markups, solve_prices
from sitescore.model.geo import project
from sitescore.model.market import build_market
from sitescore.model.site import evaluate_site
from sitescore.model.types import Site

CFG, REGION = load_model_config(), load_region()
CAFE = load_business_type("cafe")
AS_OF = dt.date(2026, 6, 1)
CBD = Site(label="CBD", lat=-33.8150, lon=151.0035)
SUBURB = Site(label="Winston Hills", lat=-33.7770, lon=150.9800)


def with_cfg(**sections):
    """Model config with some sub-fields overridden, e.g. abm={'heterogeneity_sigma': 0}."""
    updates = {k: getattr(CFG, k).model_copy(update=v) for k, v in sections.items()}
    return CFG.model_copy(update=updates)


def with_profile(profile=CAFE, **sections):
    updates = {k: getattr(profile, k).model_copy(update=v) for k, v in sections.items()}
    return profile.model_copy(update=updates)


@pytest.fixture(scope="module")
def market(mock_store):
    return build_market(mock_store.as_of(AS_OF), CAFE, CFG, REGION)


def choice_model(market, site, profile, cfg):
    xs, ys = project([site.lon], [site.lat], REGION.metric_crs)
    sx, sy = float(xs[0]), float(ys[0])
    d = compute_demand(sx, sy, market, profile, cfg)
    f = compute_fit(d.catchment, market, profile)
    agents = build_agents(d.catchment, f.point_multiplier, cfg)
    return ChoiceModel(agents, build_stores(sx, sy, d.catchment, market, profile, cfg), profile, cfg)


def layers(result):
    return {layer.key: layer for layer in result.layers}


def test_agents_reduce_to_huff_when_tastes_quality_and_price_are_neutral(market):
    cfg = with_cfg(abm={"heterogeneity_sigma": 0.0}, game={"enabled": False})
    profile = with_profile(our_store={"quality": 0.0})
    model = choice_model(market, CBD, profile, cfg)
    prices = np.full(len(model.stores), profile.pricing.reference_price)
    np.testing.assert_allclose(model.probabilities(prices), model.huff_probabilities(), atol=1e-12)
    result = layers(evaluate_site(market, CBD, profile, cfg, REGION))
    assert result["behaviour"].factor == pytest.approx(1.0, abs=1e-9)
    assert result["price"].factor == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("quality, direction", [(0.5, 1), (-0.5, -1)])
def test_quality_moves_behaviour_factor(market, quality, direction):
    profile = with_profile(our_store={"quality": quality})
    cfg = with_cfg(abm={"heterogeneity_sigma": 0.0})
    b = layers(evaluate_site(market, CBD, profile, cfg, REGION))["behaviour"].factor
    assert (b - 1) * direction > 0.05


def test_ramp_follows_awareness_without_habit_and_lags_it_with_habit(market):
    awareness = ramp_curve(CFG.horizon_months, CAFE.dynamics)
    no_habit = evaluate_site(market, CBD, CAFE, with_cfg(abm={"monthly_reconsider_share": 1.0}), REGION)
    np.testing.assert_allclose(no_habit.ramp, awareness, rtol=1e-9)
    sticky = evaluate_site(market, CBD, CAFE, with_cfg(abm={"monthly_reconsider_share": 0.3}), REGION)
    assert np.all(np.array(sticky.ramp) <= awareness + 1e-12)
    assert sticky.ramp[0] < no_habit.ramp[0] and sticky.ramp[-1] > 0.95


def test_backed_out_costs_make_todays_prices_an_equilibrium(market):
    model = choice_model(market, CBD, CAFE, CFG)
    start = np.full(len(model.stores), CAFE.pricing.reference_price)
    m = markups(model, start, ours_available=False)
    costs = CAFE.pricing.reference_price * (1 - m)
    near = (model.stores.site_dist_m <= CFG.game.radius_m) & (m < 0.95)
    near[0] = False
    np.testing.assert_allclose(costs[near] / (1 - m[near]), CAFE.pricing.reference_price)


def test_competitors_cut_prices_when_we_open_and_the_game_converges(market):
    """On average rivals cut; the one losing most to us cuts most.

    A few may nudge prices up: we take their most price-sensitive nearby
    customers, leaving a more loyal base (a known effect with varied customers).
    """
    model = choice_model(market, CBD, CAFE, CFG)
    g = solve_prices(model, CAFE, CFG)
    rivals = np.array([i for i in g.players if i != 0])
    assert g.converged and len(rivals) > 0
    change = g.prices_after[rivals] / g.prices_before[rivals] - 1
    assert change.mean() < 0 and change.max() < 0.02
    # The rival we take most customers from responds most.
    before = model.customers(model.probabilities(g.prices_before, ours_available=False))
    after = model.customers(model.probabilities(g.prices_before, ours_available=True))
    hit = rivals[np.argmax((before - after)[rivals] / before[rivals])]
    assert g.prices_after[hit] < g.prices_before[hit]
    assert g.prices_after[0] == CAFE.pricing.our_price  # optimise_our_price is off by default
    lo, hi = CAFE.pricing.price_range
    assert np.all((g.prices_after >= lo - 1e-9) & (g.prices_after <= hi + 1e-9))


def test_more_price_sensitive_customers_mean_lower_prices(market):
    soft = solve_prices(choice_model(market, CBD, CAFE, CFG), CAFE, CFG)
    sharp_profile = with_profile(pricing={"price_elasticity": 4.0})
    sharp = solve_prices(choice_model(market, CBD, sharp_profile, CFG), sharp_profile, CFG)
    assert sharp.suggested_price < soft.suggested_price


def test_revenue_still_exact_product_with_agents_and_game(market):
    for site in (CBD, SUBURB):
        r = evaluate_site(market, site, CAFE, CFG, REGION)
        assert {"behaviour", "price"} <= set(layers(r))
        assert math.prod(layer.factor for layer in r.layers) == pytest.approx(r.monthly_revenue)
        assert len(r.ramp) == CFG.horizon_months


def test_agents_can_be_switched_off(market):
    r = evaluate_site(market, CBD, CAFE, with_cfg(abm={"enabled": False}), REGION)
    assert "behaviour" not in layers(r) and r.ramp is None
    assert math.prod(layer.factor for layer in r.layers) == pytest.approx(r.monthly_revenue)


def test_agent_results_are_deterministic(market):
    assert evaluate_site(market, CBD, CAFE, CFG, REGION) == evaluate_site(market, CBD, CAFE, CFG, REGION)
