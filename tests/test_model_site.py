"""End-to-end single-site evaluation on the mock dataset."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from sitescore.config import load_business_type, load_model_config, load_region
from sitescore.datastore import NoDataAsOf
from sitescore.model.market import build_market
from sitescore.model.site import evaluate_site
from sitescore.model.types import Site

CFG, REGION = load_model_config(), load_region()
AS_OF = dt.date(2026, 6, 1)
CBD = Site(label="CBD", lat=-33.8150, lon=151.0035)
SUBURB = Site(label="Winston Hills", lat=-33.7770, lon=150.9800)


@pytest.fixture(scope="module")
def cafe_market(mock_store):
    return build_market(mock_store.as_of(AS_OF), load_business_type("cafe"), CFG, REGION)


def evaluate(market, site, type_id="cafe"):
    return evaluate_site(market, site, load_business_type(type_id), CFG, REGION)


def test_revenue_is_exact_product_of_layer_factors(cafe_market):
    rng = np.random.default_rng(3)
    lon_min, lat_min, lon_max, lat_max = REGION.bbox
    for lat, lon in zip(rng.uniform(lat_min, lat_max, 25), rng.uniform(lon_min, lon_max, 25),
                        strict=True):
        r = evaluate(cafe_market, Site(lat=lat, lon=lon))
        assert math.prod(layer.factor for layer in r.layers) == pytest.approx(r.monthly_revenue)


def test_dense_centre_beats_low_density_suburb(cafe_market):
    assert evaluate(cafe_market, CBD).monthly_revenue > 5 * evaluate(cafe_market, SUBURB).monthly_revenue


def test_results_are_deterministic(cafe_market):
    assert evaluate(cafe_market, CBD) == evaluate(cafe_market, CBD)


def test_result_records_data_cut_off(cafe_market):
    r = evaluate(cafe_market, CBD)
    used = {d.table for d in r.data_used}
    assert {"areas", "workers", "station_usage", "pois"} <= used
    assert all(d.latest_published <= AS_OF for d in r.data_used)


def test_excluded_venue_is_not_a_competitor(mock_store, cafe_market):
    nearest = cafe_market.competitors.ids[0]
    m = build_market(mock_store.as_of(AS_OF), load_business_type("cafe"), CFG, REGION,
                     exclude_osm_ids=(nearest,))
    assert nearest not in set(m.competitors.ids)
    assert len(m.competitors) == len(cafe_market.competitors) - 1


def test_model_cannot_run_before_data_was_published(mock_store):
    # Census workers were published 12 Oct 2022.
    with pytest.raises(NoDataAsOf):
        build_market(mock_store.as_of(dt.date(2022, 9, 1)), load_business_type("cafe"), CFG, REGION)


@pytest.mark.parametrize("type_id", ["gym", "childcare"])
def test_other_business_types_run_from_config_alone(mock_store, type_id):
    profile = load_business_type(type_id)
    m = build_market(mock_store.as_of(AS_OF), profile, CFG, REGION)
    r = evaluate_site(m, CBD, profile, CFG, REGION)
    assert r.monthly_revenue > 0
    if type_id == "childcare":  # residents are counted as children aged 0-4
        assert m.residents.people.sum() < 0.15 * build_market(
            mock_store.as_of(AS_OF), load_business_type("cafe"), CFG, REGION).residents.people.sum()
