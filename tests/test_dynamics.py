"""Time dynamics, multi-site simulation and the 'why' attribution."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from sitescore.config import load_business_type, load_calendar, load_model_config, load_region
from sitescore.model.dynamics import (
    development_schedule,
    month_starts,
    new_residents,
    ramp_curve,
    seasonal_factors,
)
from sitescore.model.market import build_market
from sitescore.model.simulate import simulate
from sitescore.model.types import Site

CFG, REGION = load_model_config(), load_region()
CAL = load_calendar(REGION.state)
CAFE = load_business_type("cafe")
AS_OF = dt.date(2026, 6, 1)
SITES = [Site(id="cbd", label="CBD", lat=-33.8150, lon=151.0035),
         Site(id="hp", label="Harris Park", lat=-33.8226, lon=151.0085),
         Site(id="wh", label="Winston Hills", lat=-33.7770, lon=150.9800)]


@pytest.fixture(scope="module")
def market(mock_store):
    return build_market(mock_store.as_of(AS_OF), CAFE, CFG, REGION)


@pytest.fixture(scope="module")
def result(market):
    return simulate(market, SITES, CAFE, CFG, REGION, CAL)


def test_ramp_starts_at_start_share_and_hits_90pct_on_time():
    r = ramp_curve(36, CAFE.dynamics)
    assert r[0] == pytest.approx(CAFE.dynamics.ramp_start_share)
    t90 = int(CAFE.dynamics.ramp_months_to_90pct)
    assert r[t90] == pytest.approx(0.9, abs=1e-9)
    assert np.all(np.diff(r) > 0) and r[-1] < 1


def test_seasonal_factors_average_one_and_dip_in_january():
    months = month_starts(dt.date(2027, 1, 1), 12)
    s = seasonal_factors(months, CAFE, CAL)
    for seg, values in s.items():
        assert values.mean() == pytest.approx(1.0), seg
    assert s["workers"][0] == s["workers"].min()  # office workers on leave in January


def test_developments_add_residents_after_completion_only(market):
    sched = development_schedule(market, CFG)
    assert (sched["completion"] > pd.Timestamp(market.census_date)).all()
    assert (sched["approved"] <= pd.Timestamp(AS_OF)).all()  # nothing approved after as-of
    months = month_starts(dt.date(2026, 7, 1), 36)
    res = new_residents(sched, months, CFG)
    t = np.array([pd.Timestamp(m) for m in months])
    for i in range(len(sched)):
        before = t < sched["completion"].iat[i]
        assert np.all(res[i, before] == 0)
        assert np.all(np.diff(res[i]) >= 0)  # occupancy only grows


def test_monthly_path_respects_totals_and_capacity(result):
    cap = CAFE.spend.capacity_visits_per_month
    for s in result.sites:
        assert len(s.months) == CFG.horizon_months
        assert s.total_revenue == pytest.approx(sum(m.revenue for m in s.months))
        assert all(m.visits <= cap + 1e-6 for m in s.months)
        assert all(0 <= m.development_revenue <= m.revenue + 1e-6 for m in s.months)
        assert s.months[0].month == dt.date(2026, 7, 1)


def test_why_reconciles_exactly_to_revenue_gap(result):
    for e in result.explanations:
        assert result.baseline_total_revenue + sum(c.dollars for c in e.contributions) \
            == pytest.approx(e.total_revenue)
        assert math.prod(c.ratio for c in e.contributions) == pytest.approx(1 + e.vs_average_pct)


def test_ranking_is_by_total_revenue(result):
    totals = {s.site.id: s.total_revenue for s in result.sites}
    assert result.ranking == sorted(totals, key=lambda k: -totals[k])
    assert result.ranking[0] == "cbd" and result.ranking[-1] == "wh"
    assert "ranks #1" in result.explanations[0].headline


def test_single_site_and_no_demand_site(market):
    lone = simulate(market, SITES[:1], CAFE, CFG, REGION, CAL)
    assert "add another site" in lone.explanations[0].headline
    nowhere = Site(id="x", label="Nowhere", lat=-33.857, lon=150.95)
    r = simulate(market, [SITES[0], nowhere], CAFE, CFG, REGION, CAL)
    assert r.ranking[-1] == "x"
    assert "no customers" in r.explanations[-1].headline


def test_cannot_open_before_as_of(market):
    with pytest.raises(ValueError):
        simulate(market, SITES, CAFE, CFG, REGION, CAL, open_date=AS_OF - dt.timedelta(days=1))
