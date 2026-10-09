"""Site-specific rent: an index on the profile's rent for a typical site."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from sitescore.config import load_business_type, load_calendar, load_model_config, load_region
from sitescore.model.demand import compute_demand
from sitescore.model.market import build_market
from sitescore.model.rent import foot_traffic, typical
from sitescore.model.simulate import simulate
from sitescore.model.site import analyse_site
from sitescore.model.types import Site

TODAY = dt.date(2026, 10, 9)
CAFE, CFG, REGION = load_business_type("cafe"), load_model_config(), load_region()
CAL = load_calendar(REGION.state)


@pytest.fixture(scope="module")
def market(mock_store):
    return build_market(mock_store.as_of(TODAY), CAFE, CFG, REGION)


def _cafe_sites(market):
    c = market.competitors
    idx = np.flatnonzero(c.primary)
    traffic = np.array([foot_traffic(compute_demand(float(c.x[i]), float(c.y[i]), market, CAFE, CFG))
                        for i in idx])
    return idx, traffic


def test_a_typical_site_pays_the_profiles_rent(market):
    typical_traffic, _ = typical(market, CAFE, CFG)
    _, traffic = _cafe_sites(market)
    assert typical_traffic == pytest.approx(np.median(traffic))


def test_busier_sites_pay_more_and_the_index_is_capped(market):
    idx, traffic = _cafe_sites(market)
    c = market.competitors
    busy, quiet = idx[np.argmax(traffic)], idx[np.argmin(traffic)]
    rent = {}
    for name, i in (("busy", busy), ("quiet", quiet)):
        r = analyse_site(market, Site(id=name, lat=float(c.lat[i]), lon=float(c.lon[i])), CAFE, CFG,
                         REGION).result
        rent[name] = r.rent
        costs = CAFE.costs
        expected = (r.monthly_revenue * (1 - costs.cogs_share) - r.rent.monthly
                    - costs.wages_per_month - costs.other_fixed_per_month)
        assert r.monthly_profit == pytest.approx(expected)  # profit uses this site's rent
    assert rent["busy"].footfall_index > rent["quiet"].footfall_index
    assert rent["busy"].monthly > rent["quiet"].monthly
    lo, hi = CFG.rent.index_range
    assert all(lo <= r.index <= hi for r in rent.values())

    tight = CFG.model_copy(update={"rent": CFG.rent.model_copy(update={"index_range": (0.9, 1.1)})})
    i = busy
    r = analyse_site(market, Site(id="t", lat=float(c.lat[i]), lon=float(c.lon[i])), CAFE, tight,
                     REGION).result
    assert 0.9 <= r.rent.index <= 1.1


def test_rent_model_off_means_the_profiles_rent_everywhere(market):
    off = CFG.model_copy(update={"rent": CFG.rent.model_copy(update={"enabled": False})})
    r = analyse_site(market, Site(id="x", lat=-33.815, lon=151.0035), CAFE, off, REGION).result
    assert r.rent is None
    c = CAFE.costs
    assert r.monthly_profit == pytest.approx(r.monthly_revenue * (1 - c.cogs_share) - c.rent_per_month
                                             - c.wages_per_month - c.other_fixed_per_month)


def test_projection_and_monte_carlo_use_the_site_rent(market):
    idx, traffic = _cafe_sites(market)
    i = idx[np.argmax(traffic)]
    site = Site(id="busy", lat=float(market.competitors.lat[i]), lon=float(market.competitors.lon[i]))
    off = CFG.model_copy(update={"rent": CFG.rent.model_copy(update={"enabled": False})})
    on_run = simulate(market, [site], CAFE, CFG, REGION, CAL, uncertainty=True, n_runs=60)
    off_run = simulate(market, [site], CAFE, off, REGION, CAL, uncertainty=True, n_runs=60)
    rent = on_run.sites[0].mature.rent
    extra = (rent.monthly - rent.base) * CFG.horizon_months
    assert off_run.sites[0].total_profit - on_run.sites[0].total_profit == pytest.approx(extra)
    p50_gap = (off_run.uncertainty.sites[0].total_profit["p50"]
               - on_run.uncertainty.sites[0].total_profit["p50"])
    assert p50_gap == pytest.approx(extra, rel=1e-6)
