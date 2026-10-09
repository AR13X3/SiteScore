"""Monte Carlo layer: sampling, exactness at the centre, agreement with full re-runs."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from sitescore.config import (
    NormalRel,
    load_business_type,
    load_calendar,
    load_model_config,
    load_region,
)
from sitescore.model.dynamics import monthly_components
from sitescore.model.market import build_market
from sitescore.model.montecarlo import (
    check_fast_supported,
    fast_site_draws,
    full_site_draws,
    sample_parameters,
)
from sitescore.model.simulate import simulate
from sitescore.model.site import analyse_site
from sitescore.model.types import Site

CFG, REGION = load_model_config(), load_region()
CAL = load_calendar(REGION.state)
CAFE = load_business_type("cafe")
AS_OF, OPEN = dt.date(2026, 6, 1), dt.date(2026, 7, 1)
SITES = [Site(id="cbd", label="CBD", lat=-33.8150, lon=151.0035),
         Site(id="hp", label="Harris Park", lat=-33.8226, lon=151.0085),
         Site(id="wh", label="Winston Hills", lat=-33.7770, lon=150.9800)]


@pytest.fixture(scope="module")
def market(mock_store):
    return build_market(mock_store.as_of(AS_OF), CAFE, CFG, REGION)


def prepared(market, site, profile=CAFE):
    a = analyse_site(market, site, profile, CFG, REGION)
    return a, monthly_components(a.result, market, profile, CFG, REGION.metric_crs, CAL, OPEN)


def test_sampling_is_reproducible_and_respects_bounds():
    d1, base = sample_parameters(CFG, CAFE, 200, seed=3)
    d2, _ = sample_parameters(CFG, CAFE, 200, seed=3)
    assert d1.keys() == d2.keys() and all(np.array_equal(d1[k], d2[k]) for k in d1)
    assert "profile.segments.workers.participation" in d1  # wildcards expanded
    for key, values in d1.items():
        if key.endswith("participation"):
            assert values.min() >= 0 and values.max() <= 1
    assert abs(np.median(d1["profile.spend.avg_transaction_value"]) - base[
        "profile.spend.avg_transaction_value"]) < 0.5


def test_unused_segment_stays_unused():
    gym = load_business_type("gym")  # commuters participation is 0
    draws, base = sample_parameters(CFG, gym, 50, seed=1)
    assert base["profile.segments.commuters.participation"] == 0
    assert np.all(draws["profile.segments.commuters.participation"] == 0)


def test_fast_mode_is_exact_at_central_values(market):
    for site in SITES:
        a, comp = prepared(market, site)
        _, base = sample_parameters(CFG, CAFE, 1, seed=0)
        central = {k: np.full(4, v) for k, v in base.items()}
        draws = fast_site_draws(a, comp, market, CAFE, CFG, central, base, 4)
        expected = simulate(market, [site], CAFE, CFG, REGION, CAL, OPEN).sites[0].months
        np.testing.assert_allclose(draws.revenue[0], [m.revenue for m in expected], rtol=1e-9)


@pytest.mark.parametrize("site", [SITES[1], SITES[2]], ids=lambda s: s.label)
def test_fast_mode_agrees_with_full_reruns(market, site):
    n = 10
    draws, base = sample_parameters(CFG, CAFE, n, seed=11)
    a, comp = prepared(market, site)
    fast = fast_site_draws(a, comp, market, CAFE, CFG, draws, base, n).revenue.sum(axis=1)
    full = full_site_draws(market, site, CAFE, CFG, REGION, CAL, OPEN, draws, n).revenue.sum(axis=1)
    error = np.abs(fast / full - 1)
    assert np.median(error) < 0.03 and error.max() < 0.06


def test_bands_and_win_chances_are_consistent(market):
    r = simulate(market, SITES, CAFE, CFG, REGION, CAL, OPEN, uncertainty=True, n_runs=120)
    u = r.uncertainty
    assert u.n_runs == 120 and len(u.sites) == len(SITES)
    assert sum(s.prob_best for s in u.sites) == pytest.approx(1.0)
    for s in u.sites:
        lo, mid, hi = (np.array(x) for x in (s.revenue.p10, s.revenue.p50, s.revenue.p90))
        assert np.all(lo <= mid + 1e-9) and np.all(mid <= hi + 1e-9)
        assert s.total_revenue["p10"] <= s.total_revenue["p50"] <= s.total_revenue["p90"]
        assert 0 <= s.prob_loss <= 1
    # Same seed, same answer.
    again = simulate(market, SITES, CAFE, CFG, REGION, CAL, OPEN, uncertainty=True, n_runs=120)
    assert again.uncertainty == u


def test_fast_mode_rejects_parameters_it_cannot_reapply():
    params = dict(CFG.montecarlo.parameters)
    params["profile.fit.strength"] = NormalRel(dist="normal_rel", sd=0.2)
    cfg = CFG.model_copy(update={"montecarlo": CFG.montecarlo.model_copy(
        update={"parameters": params})})
    with pytest.raises(ValueError, match="mode: full"):
        check_fast_supported(cfg)
