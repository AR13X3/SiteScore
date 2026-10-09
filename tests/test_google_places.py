"""Google Places adapter, offline: Google's API is replaced by a fake."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import shutil

import pytest

import sitescore.pipeline.google_places as gp
from sitescore.datastore import DataStore


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body


@pytest.fixture
def real_map_ctx(mock_store, ctx, tmp_path):
    """A context whose store has a 'real' map (the mock one, relabelled) and a key."""
    store = DataStore(tmp_path / "store")
    shutil.copytree(mock_store.root, store.root)
    store.write("pois", mock_store.read("pois"), "real")
    settings = ctx.settings.model_copy(update={"google_places_api_key": "test-key"})
    return dataclasses.replace(ctx, store=store, settings=settings, raw_dir=tmp_path / "raw")


def test_best_match_needs_name_and_proximity():
    places = [
        {"id": "far", "displayName": {"text": "Bean Espresso"},
         "location": {"latitude": -33.80, "longitude": 151.02}},
        {"id": "other", "displayName": {"text": "Totally Different"},
         "location": {"latitude": -33.8150, "longitude": 151.0035}},
        {"id": "ok", "displayName": {"text": "Bean Espresso Parramatta"},
         "location": {"latitude": -33.8151, "longitude": 151.0036}},
    ]
    assert gp.best_match("Bean Espresso", -33.8150, 151.0035, places)["id"] == "ok"
    assert gp.best_match("Unknown Café", -33.8150, 151.0035, places) is None


def test_fetch_matches_caches_and_respects_the_request_cap(real_map_ctx, monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        body = kwargs["json"]
        calls.append(body["textQuery"])
        centre = body["locationBias"]["circle"]["center"]
        return FakeResponse({"places": [{
            "id": f"g-{len(calls)}", "displayName": {"text": body["textQuery"]},
            "location": {"latitude": centre["latitude"], "longitude": centre["longitude"]},
            "rating": 4.4, "userRatingCount": 120, "businessStatus": "OPERATIONAL"}]})

    monkeypatch.setattr(gp, "request", fake_request)
    extra = real_map_ctx.source("google_places").model_extra
    monkeypatch.setitem(extra, "max_requests", 5)

    places = gp.GooglePlaces().fetch(real_map_ctx)["places"]
    assert len(calls) == 5 and len(places) == 5
    assert set(places["business_status"]) == {"OPERATIONAL"}

    gp.GooglePlaces().fetch(real_map_ctx)  # second run: answers come from the cache
    assert len(calls) == 5

    later = dataclasses.replace(real_map_ctx, today=real_map_ctx.today + dt.timedelta(days=31))
    gp.GooglePlaces().fetch(later)  # cache older than 30 days: asked again
    assert len(calls) == 10


def test_fetch_refuses_without_a_real_map(ctx, mock_store):
    settings = ctx.settings.model_copy(update={"google_places_api_key": "test-key"})
    with pytest.raises(RuntimeError, match="real OSM map"):
        gp.GooglePlaces().fetch(dataclasses.replace(ctx, store=mock_store, settings=settings))


def test_lookup_list_includes_businesses_that_have_since_closed(mock_store):
    pois = mock_store.read("pois")
    todo = gp.businesses_to_look_up(pois, dt.date(2022, 1, 1))
    latest_ids = set(pois.loc[pois["version"] == pois["version"].max(), "osm_id"])
    assert any(osm_id not in latest_ids for osm_id in todo["osm_id"])
    assert all(json.loads(t).get("amenity") in ("cafe", "childcare") or
               json.loads(t).get("leisure") == "fitness_centre" for t in todo["tags"])
