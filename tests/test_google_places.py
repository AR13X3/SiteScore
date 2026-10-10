"""Google Places adapter, offline: Google's API is replaced by a fake."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import shutil

import pandas as pd
import pytest

import sitescore.pipeline.google_places as gp
from sitescore.datastore import DataStore
from sitescore.pipeline.base import KeepExisting, run_adapter


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body


class FakeGoogle:
    """Answers every Text Search with the business itself, where it was asked."""

    def __init__(self, fail_on: int | None = None):
        self.queries: list[str] = []
        self.fail_on = fail_on

    def __call__(self, method, url, **kwargs):
        body = kwargs["json"]
        self.queries.append(body["textQuery"])
        if len(self.queries) == self.fail_on:
            raise gp.httpx.ConnectError("network down")
        centre = body["locationBias"]["circle"]["center"]
        return FakeResponse({"places": [{
            "id": f"g-{len(self.queries)}", "displayName": {"text": body["textQuery"]},
            "location": {"latitude": centre["latitude"], "longitude": centre["longitude"]},
            "rating": 4.4, "userRatingCount": 120, "businessStatus": "OPERATIONAL"}]})


@pytest.fixture
def real_map_ctx(mock_store, ctx, tmp_path):
    """A context whose store has a 'real' map (the mock one, relabelled) and a key."""
    store = DataStore(tmp_path / "store")
    shutil.copytree(mock_store.root, store.root)
    store.write("pois", mock_store.read("pois"), "real")
    settings = ctx.settings.model_copy(update={"google_places_api_key": "test-key"})
    return dataclasses.replace(ctx, store=store, settings=settings, raw_dir=tmp_path / "raw",
                               repo_raw_dir=tmp_path / "repo_raw")


@pytest.fixture
def five_businesses(monkeypatch):
    """Look up only the first five businesses on the map."""
    original = gp.businesses_to_look_up
    monkeypatch.setattr(gp, "businesses_to_look_up", lambda pois, since: original(pois, since).head(5))


@pytest.fixture
def google(monkeypatch) -> FakeGoogle:
    fake = FakeGoogle()
    monkeypatch.setattr(gp, "request", fake)
    return fake


def ledger(ctx) -> dict:
    return json.loads((ctx.repo_raw_dir / "google_places" / "ledger.json").read_text())


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


def test_best_match_ignores_apostrophes_and_accents():
    """'Nadia's' and 'Joe's Café' only share the 's' of the apostrophe; 'Café Bella'
    and 'Café Roma' only share 'caf' once the accent is dropped."""
    here = {"latitude": -33.8150, "longitude": 151.0035}
    assert gp.best_match("Nadia's", -33.8150, 151.0035,
                         [{"id": "x", "displayName": {"text": "Joe's Café"}, "location": here}]) is None
    assert gp.best_match("Café Bella", -33.8150, 151.0035,
                         [{"id": "x", "displayName": {"text": "Café Roma"}, "location": here}]) is None
    assert gp.best_match("Nadia’s Café", -33.8150, 151.0035,
                         [{"id": "ok", "displayName": {"text": "Nadias Cafe"},
                           "location": here}])["id"] == "ok"



def test_best_match_spacing_neighbours_answers_and_big_buildings():
    here = {"latitude": -33.8150, "longitude": 151.0035}
    shot = {"id": "shot", "displayName": {"text": "Cafe Long Shot"}, "location": here}
    assert gp.best_match("Longshot Cafe", -33.8150, 151.0035, [shot])["id"] == "shot"
    # Only in another query's answer: found through the pool.
    xa = {"id": "xa", "displayName": {"text": "XA Expresso"}, "location": here}
    assert gp.best_match("XA Expresso", -33.8150, 151.0035, [], pool=[xa])["id"] == "xa"
    # 200 m away: too far for a partial name, close enough for exactly the same name.
    far = {"latitude": -33.8150 + 200 / 110_500, "longitude": 151.0035}
    crunch = {"id": "c", "displayName": {"text": "Crunch Fitness Parramatta"}, "location": far}
    assert gp.best_match("Crunch Fitness Parramatta", -33.8150, 151.0035, [crunch])["id"] == "c"
    assert gp.best_match("Crunch Fitness", -33.8150, 151.0035, [crunch]) is None

def test_google_weekly_hours():
    day = [{"open": {"day": d, "hour": 7, "minute": 0}, "close": {"day": d, "hour": 15, "minute": 30}}
           for d in range(1, 6)]
    assert gp.google_weekly_hours({"periods": day}) == 42.5
    late = [{"open": {"day": 5, "hour": 18, "minute": 0}, "close": {"day": 6, "hour": 2, "minute": 0}}]
    assert gp.google_weekly_hours({"periods": late}) == 8.0
    assert gp.google_weekly_hours({"periods": [{"open": {"day": 0, "hour": 0}}]}) == 168.0
    assert gp.google_weekly_hours(None) is None


def test_fetch_matches_caches_and_counts_every_request(real_map_ctx, five_businesses, google):
    places = gp.GooglePlaces().fetch(real_map_ctx)["places"]
    assert len(google.queries) == 5 and len(places) == 5
    assert set(places["business_status"]) == {"OPERATIONAL"}
    assert ledger(real_map_ctx)["total"] == 5

    gp.GooglePlaces().fetch(real_map_ctx)  # second run: answers come from the cache
    assert len(google.queries) == 5 and ledger(real_map_ctx)["total"] == 5

    later = dataclasses.replace(real_map_ctx, today=real_map_ctx.today + dt.timedelta(days=31))
    gp.GooglePlaces().fetch(later)  # cache older than 30 days: asked again
    assert len(google.queries) == 10
    assert ledger(real_map_ctx)["total"] == 10
    assert [r["requests"] for r in ledger(real_map_ctx)["runs"]] == [5, 5]


def test_ledger_refuses_a_run_that_would_pass_the_limit(real_map_ctx, five_businesses, google,
                                                       monkeypatch):
    monkeypatch.setitem(real_map_ctx.source("google_places").model_extra, "max_requests", 7)
    gp.GooglePlaces().fetch(real_map_ctx)
    assert ledger(real_map_ctx)["total"] == 5

    later = dataclasses.replace(real_map_ctx, today=real_map_ctx.today + dt.timedelta(days=31))
    with pytest.raises(RuntimeError, match="5 requests needed but only 2 of 7 left"):
        gp.GooglePlaces().fetch(later)
    assert len(google.queries) == 5  # refused before sending anything
    assert ledger(real_map_ctx)["total"] == 5


def test_ledger_never_allows_more_than_400(tmp_path, monkeypatch):
    book = gp.RequestLedger(tmp_path / "ledger.json", limit=10_000)
    assert book.limit == 400
    book.note(dt.date(2026, 10, 10), 399, "test")
    book.reserve(dt.date(2026, 10, 10))
    with pytest.raises(RuntimeError, match="refusing"):
        book.reserve(dt.date(2026, 10, 10))
    assert gp.RequestLedger(tmp_path / "ledger.json", limit=400).total == 400


def test_a_failed_request_is_counted_and_a_rerun_sends_only_the_rest(real_map_ctx,
                                                                     five_businesses, monkeypatch):
    flaky = FakeGoogle(fail_on=3)
    monkeypatch.setattr(gp, "request", flaky)
    with pytest.raises(gp.httpx.ConnectError):
        gp.GooglePlaces().fetch(real_map_ctx)
    assert len(flaky.queries) == 3 and ledger(real_map_ctx)["total"] == 3  # no retries

    steady = FakeGoogle()
    monkeypatch.setattr(gp, "request", steady)
    assert len(gp.GooglePlaces().fetch(real_map_ctx)["places"]) == 5
    assert len(steady.queries) == 3  # the failed one and the two never sent
    assert ledger(real_map_ctx)["total"] == 6


def test_the_same_business_twice_costs_one_request(real_map_ctx, google, monkeypatch):
    twins = pd.DataFrame({
        "osm_id": ["node/1", "way/2", "node/3"],
        "name": ["Gloria Jean's", "Gloria Jeans", "Gloria Jean's"],
        "lat": [-33.8150, -33.8152, -33.8300], "lon": [151.0035, 151.0036, 151.0035],
    })
    monkeypatch.setattr(gp, "businesses_to_look_up", lambda pois, since: twins)
    places = gp.GooglePlaces().fetch(real_map_ctx)["places"]
    assert len(google.queries) == 2  # node/3 is 1.7 km away: a different outlet
    assert set(places["osm_id"]) == {"node/1", "way/2", "node/3"}


def test_fresh_places_table_is_kept_without_any_request(real_map_ctx, five_businesses, google):
    store = real_map_ctx.store
    run_adapter(gp.GooglePlaces(), store, real_map_ctx)
    assert len(google.queries) == 5 and store.provenance("places") == "real"
    path = store.root / "places.real.parquet"
    written, catalog = path.stat().st_mtime, store.catalog()

    # 29 days later, even with the raw cache deleted: nothing is fetched or written.
    for f in (real_map_ctx.repo_raw_dir / "google_places").glob("*_*.json"):
        f.unlink()
    soon = dataclasses.replace(real_map_ctx, today=real_map_ctx.today + dt.timedelta(days=29))
    with pytest.raises(KeepExisting, match="under 30 days old"):
        gp.GooglePlaces().fetch(soon)
    [result] = run_adapter(gp.GooglePlaces(), store, soon)
    assert result.provenance == "real" and result.note.startswith("kept")
    assert len(google.queries) == 5
    assert path.stat().st_mtime == written and store.catalog() == catalog  # no mock either

    # --force refetches (the raw cache was deleted, so Google is asked again).
    run_adapter(gp.GooglePlaces(), store, dataclasses.replace(soon, force=True))
    assert len(google.queries) == 10

    # 30 days after the data was fetched, it's no longer kept.
    month = dataclasses.replace(real_map_ctx, today=real_map_ctx.today + dt.timedelta(days=60))
    run_adapter(gp.GooglePlaces(), store, month)
    assert len(google.queries) == 15


def test_old_machine_local_cache_is_moved_and_counted(real_map_ctx, five_businesses, google):
    todo = gp.businesses_to_look_up(real_map_ctx.store.read("pois"), dt.date(2022, 1, 1))
    old = real_map_ctx.raw_dir / "google_places"
    old.mkdir(parents=True)
    b = todo.iloc[0]
    gp.cache_path(old, b["osm_id"], b["name"]).write_text(json.dumps({
        "fetched": real_map_ctx.today.isoformat(), "places": []}))
    gp.GooglePlaces().fetch(real_map_ctx)
    assert len(google.queries) == 4  # the moved answer is reused
    assert not list(old.glob("*.json"))
    assert ledger(real_map_ctx)["total"] == 5  # 1 found in the old cache + 4 sent


def test_fetch_refuses_without_a_real_map(ctx, mock_store):
    settings = ctx.settings.model_copy(update={"google_places_api_key": "test-key"})
    with pytest.raises(RuntimeError, match="real OSM map"):
        gp.GooglePlaces().fetch(dataclasses.replace(ctx, store=mock_store, settings=settings))


def test_tests_never_see_the_real_key(ctx):
    assert not ctx.settings.google_places_api_key
    assert "repo_raw" in str(ctx.repo_raw_dir)


def test_lookup_list_includes_businesses_that_have_since_closed(mock_store):
    pois = mock_store.read("pois")
    todo = gp.businesses_to_look_up(pois, dt.date(2022, 1, 1))
    latest_ids = set(pois.loc[pois["version"] == pois["version"].max(), "osm_id"])
    assert any(osm_id not in latest_ids for osm_id in todo["osm_id"])
    assert all(json.loads(t).get("amenity") in ("cafe", "childcare") or
               json.loads(t).get("leisure") == "fitness_centre" for t in todo["tags"])


def test_backtest_ignores_real_places_data_past_googles_30_days(mock_store, tmp_path):
    """Google's terms allow keeping Places content 30 days: after that the backtest stops
    using it (and says how to delete it) rather than scoring with expired data."""
    from sitescore.backtest.outcomes import OutcomeTables
    store = DataStore(tmp_path / "store")
    shutil.copytree(mock_store.root, store.root)
    for table in ("pois", "places"):
        store.write(table, mock_store.read(table), "real")
    fetched = pd.Timestamp(store.read("places")["version"].min()).date()
    assert OutcomeTables.load(store, fetched + dt.timedelta(days=30)).places is not None
    assert OutcomeTables.load(store, fetched + dt.timedelta(days=31)).places is None
    # mock data never expires (it isn't Google's)
    assert OutcomeTables.load(mock_store, fetched + dt.timedelta(days=400)).places is not None
