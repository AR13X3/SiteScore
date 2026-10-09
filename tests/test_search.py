"""Spot finder: candidates in a user-drawn circle, quick screen, full model on a shortlist."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sitescore.api.deps import get_store
from sitescore.api.main import app
from sitescore.config import load_business_type, load_calendar, load_model_config, load_region
from sitescore.model.market import build_market
from sitescore.model.search import Area, find_spots, grid_candidates, metres, spread
from sitescore.model.simulate import simulate
from sitescore.model.types import Site
from sitescore.pipeline.osm_vacancies import vacancy

TODAY = dt.date(2026, 10, 9)
CAFE, CFG, REGION = load_business_type("cafe"), load_model_config(), load_region()
CAL = load_calendar(REGION.state)
CBD = Area(-33.8150, 151.0035, 800)


@pytest.fixture(scope="module")
def market(mock_store):
    return build_market(mock_store.as_of(TODAY), CAFE, CFG, REGION)


@pytest.fixture(scope="module")
def client(mock_store):
    app.dependency_overrides[get_store] = lambda: mock_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize("tags, found", [
    ({"shop": "vacant"}, ("Vacant shop", "")),
    ({"disused:amenity": "cafe", "name": "Old Cafe"}, ("Former café", "cafe")),
    ({"disused:shop": "mobile_phone"}, ("Former shop (mobile phone)", "mobile_phone")),
    ({"disused:shop": "yes"}, ("Vacant shop", "")),
    ({"disused:amenity": "parking"}, None),                       # not a shopfront
    ({"disused:amenity": "cafe", "amenity": "restaurant"}, None),  # it's trading again
])
def test_vacancy_classification(tags, found):
    assert vacancy(tags) == found


def test_grid_stays_in_the_circle_and_on_shopping_strips(market):
    everywhere = grid_candidates(CBD, market, REGION, CFG, retail_only=False)
    strips = grid_candidates(CBD, market, REGION, CFG, retail_only=True)
    assert 0 < len(strips) <= len(everywhere) <= CFG.search.grid_points * 1.3
    for c in everywhere:
        assert metres(CBD.lat, CBD.lon, c.lat, c.lon) <= CBD.radius_m
    for c in strips:
        d = metres(c.lat, c.lon, market.competitors.lat, market.competitors.lon)
        assert d.min() <= CFG.search.retail_within_m


def test_spread_keeps_suggestions_apart():
    lat = np.array([0.0, 0.0001, 0.01, 0.0002])
    lon = np.zeros(4)
    assert spread(np.arange(4), lat, lon, k=3, min_sep_m=150) == [0, 2]
    assert spread(np.arange(4), lat, lon, k=3, min_sep_m=0) == [0, 1, 2]


def test_bands_only_for_the_best_sites(market):
    sites = [Site(id=f"s{i}", lat=CBD.lat + 0.004 * i, lon=CBD.lon) for i in range(4)]
    r = simulate(market, sites, CAFE, CFG, REGION, CAL, uncertainty=True, uncertainty_top=2)
    banded = {u.site_id for u in r.uncertainty.sites}
    best = {s.site.id for s in sorted(r.sites, key=lambda s: s.total_revenue, reverse=True)[:2]}
    assert banded == best and len(r.sites) == 4


def test_find_spots_ranks_a_spread_shortlist(market):
    cands = grid_candidates(CBD, market, REGION, CFG, retail_only=False)
    found = find_spots(market, cands, CAFE, CFG, REGION, CAL)
    assert len(found.quick) == len(cands) and len(found.shortlisted) <= CFG.search.shortlist
    assert len(found.top.uncertainty.sites) == min(CFG.search.results, len(found.shortlisted))
    # the shortlist really is the quick screen's best (apart from spacing)
    best_quick = max(found.quick)
    assert found.quick[[c.id for c in cands].index(found.shortlisted[0])] == best_quick


def test_search_endpoint(client):
    body = {"lat": CBD.lat, "lon": CBD.lon, "radius_m": 1500}
    r = client.post("/api/search", json={**body, "where": "anywhere", "rank_by": "profit"}).json()
    assert r["n_candidates"] > 0 and 0 < len(r["spots"]) <= CFG.search.results
    assert [s["rank"] for s in r["spots"]] == list(range(1, len(r["spots"]) + 1))
    profits = [s["total_profit"] for s in r["spots"]]
    assert profits == sorted(profits, reverse=True)
    assert r["grid"] and any("estimated rent" in n for n in r["notes"])
    assert all(s["rent_monthly"] > 0 for s in r["spots"])

    v = client.post("/api/search", json={**body, "where": "vacant"}).json()
    assert v["grid"] == [] and all(s["kind"] != "Location" for s in v["spots"])
    assert len(v["vacancies"]) == v["n_candidates"]


def test_search_limits_and_history(client):
    too_big = client.post("/api/search", json={"lat": CBD.lat, "lon": CBD.lon, "radius_m": 99_999})
    assert too_big.status_code == 422
    past = client.post("/api/search", json={"lat": CBD.lat, "lon": CBD.lon, "radius_m": 1500,
                                            "where": "vacant", "as_of": "2024-06-01"}).json()
    assert past["spots"] == [] and any("vacancy data only exists" in n for n in past["notes"])


def test_vacancies_dont_hold_back_when_the_model_can_run(mock_store):
    """Vacancies are only published 'today'; they list candidates and aren't a model input."""
    from sitescore.backtest.cohort import data_ready_date
    assert mock_store.read("vacancies")["published_at"].min().date() == TODAY
    assert data_ready_date(mock_store) < dt.date(2023, 1, 1)
