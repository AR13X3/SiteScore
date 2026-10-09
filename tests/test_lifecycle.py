"""Business lifecycles from OSM element histories, fixed-horizon survival, opening checks."""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from sitescore.backtest import lifecycle
from sitescore.backtest.cohort import Business, discover_from_osm
from sitescore.backtest.metrics import closure_by_third
from sitescore.backtest.openings import check
from sitescore.backtest.outcomes import _horizon, _Sources
from sitescore.config import load_backtest_config, load_business_type
from sitescore.datastore import DataStore

BT, CAFE = load_backtest_config(), load_business_type("cafe")
TODAY = dt.date(2026, 10, 10)
SNAPS = pd.date_range("2022-01-01", "2026-10-01", freq="QS")
LAT, LON = -33.8150, 151.0000
M_LON = 1 / 92_600   # degrees of longitude per metre (as in sitescore.matching)


def cafe(name: str, **extra) -> dict:
    return {"amenity": "cafe", "name": name, **extra}


def make_store(tmp_path, elements) -> DataStore:
    """elements: (osm_id, metres east of the origin, [(date, tags or None=deleted), ...]).
    Snapshots show what an Overpass query for cafés would have returned."""
    pois, hist = [], []
    for osm_id, east, versions in elements:
        lon = LON + east * M_LON
        for seq, (when, tags) in enumerate(versions, 1):
            t = pd.Timestamp(when)
            hist.append({"osm_id": osm_id, "seq": seq, "name": (tags or {}).get("name", ""),
                         "lon": lon, "lat": LAT, "tags": json.dumps(tags or {}),
                         "deleted": tags is None, "changeset": 0, "published_at": t,
                         "valid_from": t, "valid_to": pd.NaT})
        for s in SNAPS:
            state = [tags for w, tags in versions if pd.Timestamp(w) <= s]
            if state and state[-1] and state[-1].get("amenity") == "cafe":
                pois.append({"osm_id": osm_id, "name": state[-1].get("name", ""), "lon": lon,
                             "lat": LAT, "tags": json.dumps(state[-1]), "version": s,
                             "published_at": s, "valid_from": s, "valid_to": pd.NaT})
    store = DataStore(tmp_path)
    store.write("pois", pd.DataFrame(pois), "real")
    store.write("poi_history", pd.DataFrame(hist), "real")
    return store


@pytest.fixture
def lc(tmp_path):
    store = make_store(tmp_path, [
        # renamed in place: one closure (replaced) and one new business
        ("node/1", 0, [("2021-03-01", cafe("Steaming Mug")), ("2023-04-13", cafe("Four Cups"))]),
        # name corrected: same business throughout
        ("node/2", 500, [("2023-05-01", cafe("Picollo Me")), ("2024-02-01", cafe("Piccolo Me"))]),
        # closed and left empty
        ("node/3", 1000, [("2021-01-01", cafe("Kokoda Cafe")),
                          ("2024-01-01", {"disused:amenity": "cafe"})]),
        # became a sandwich bar
        ("node/4", 1500, [("2021-01-01", cafe("Hudsons")),
                          ("2026-06-06", {"amenity": "fast_food", "name": "Matty's"})]),
        # same business retagged as a restaurant: not a closure
        ("node/5", 2000, [("2021-01-01", cafe("Bella")),
                          ("2024-01-01", {"amenity": "restaurant", "name": "Bella"})]),
        # point deleted, same café redrawn 20 m away a month later: re-mapped
        ("node/6", 2500, [("2021-01-01", cafe("Gatehouse")), ("2023-03-01", None)]),
        ("way/7", 2520, [("2023-04-01", cafe("Gatehouse"))]),
        # deleted, and a different café opened at the same spot: replaced
        ("node/8", 3000, [("2019-01-01", cafe("Cafe Centro")), ("2024-06-04", None)]),
        ("node/9", 3010, [("2024-05-31", cafe("Chaffee House"))]),
        # deleted with nothing after it
        ("node/10", 3500, [("2020-01-01", cafe("Lipari")), ("2026-07-27", None)]),
    ])
    return store, lifecycle.build(store, CAFE, BT.survival)


def _run(lc, osm_id, name):
    return lc.set_index("run_id").loc[lifecycle.run_for(lc, osm_id, name, TODAY)]


def test_how_businesses_end(lc):
    _, lc = lc
    mug = _run(lc, "node/1", "Steaming Mug")
    assert mug["kind"] == "replaced" and mug["closed"] == pd.Timestamp("2023-04-13")
    cups = _run(lc, "node/1", "Four Cups")
    assert cups["predecessor"] == "Steaming Mug" and pd.isna(cups["closed"])
    assert pd.isna(_run(lc, "node/2", "Piccolo Me")["closed"])          # a correction
    assert _run(lc, "node/3", "Kokoda Cafe")["kind"] == "vacant"
    hudsons = _run(lc, "node/4", "Hudsons")
    assert hudsons["kind"] == "other_use" and "fast_food" in hudsons["detail"]
    assert pd.isna(_run(lc, "node/5", "Bella")["closed"])               # retagged, same business
    centro = _run(lc, "node/8", "Cafe Centro")
    assert centro["kind"] == "replaced" and centro["successor"] == "Chaffee House"
    assert _run(lc, "node/9", "Chaffee House")["predecessor"] == "Cafe Centro"
    assert _run(lc, "node/10", "Lipari")["kind"] == "removed"
    assert lifecycle.failure_type("replaced") == "operator"
    assert lifecycle.failure_type("vacant") == lifecycle.failure_type("other_use") == "site"


def test_remapping_is_not_a_closure_and_is_followed(lc):
    _, lc = lc
    old = _run(lc, "node/6", "Gatehouse")
    assert pd.isna(old["closed"]) and old["continued_as"].startswith("way/7")
    fate = lifecycle.fate(lc, old.name)
    assert fate.closed is None and fate.on_map_today


def test_site_closures_count_every_business_that_ended_at_the_spot(lc):
    _, lc = lc
    spot = lifecycle.site_closures(lc, LAT, LON + 3005 * M_LON, BT.survival.site_radius_m)
    assert list(spot["name"]) == ["Cafe Centro"]


def test_takeovers_are_discovered_as_openings(lc):
    store, lc = lc
    found = {b.name: b for b in discover_from_osm(store, CAFE, BT, lc)}
    cups = found["Four Cups"]
    assert cups.opened == dt.date(2023, 4, 13) and cups.as_of < cups.opened
    assert "taking over from 'Steaming Mug'" in cups.opened_note
    assert "Piccolo Me" in found       # first mapped in the window (an opening check decides)


# --- Opening check ----------------------------------------------------------------------


def _biz(name, east, opened="2023-06-01", osm_id=""):
    d = dt.date.fromisoformat(opened)
    return Business(name, LAT, LON + east * M_LON, d, d - dt.timedelta(days=1), osm_id=osm_id)


def test_opening_check(lc):
    _, lc = lc
    fsq = pd.DataFrame({"name": ["Old Corner"], "lat": [LAT], "lon": [LON + 4000 * M_LON],
                        "date_created": [pd.Timestamp("2014-01-01")]})
    asic = pd.DataFrame({"bn_name": ["NEW BEAN"], "registered": [pd.Timestamp("2016-01-01")]})
    assert check(_biz("Four Cups", 0, "2023-04-13", "node/1"), lc, fsq, asic, BT).verdict == "new"
    assert check(_biz("Chaffee House", 3010, "2024-05-31", "node/9"), lc, fsq, asic,
                 BT).verdict == "new"
    assert check(_biz("Gatehouse", 2520, "2023-04-01", "way/7"), lc, fsq, asic,
                 BT).verdict == "remapped"
    assert check(_biz("Old Corner", 4000), lc, fsq, asic, BT).verdict == "older"
    recent = fsq.assign(date_created=pd.Timestamp("2023-03-01"))
    assert check(_biz("Old Corner", 4000), lc, recent, asic, BT).verdict == "new"
    # ASIC has no addresses: an old same-named registration may be another outlet
    assert check(_biz("New Bean", 5000), lc, fsq, asic, BT).verdict == "unverified"


# --- Fixed-horizon survival --------------------------------------------------------------


def _fate(closed=None, kind=None, last_edit=None, on_map=None):
    ts = (lambda d: pd.Timestamp(d) if d else None)
    return lifecycle.Fate("x#0", ts(closed), kind, "detail", "", ts(last_edit), None,
                          closed is None if on_map is None else on_map)


def _src(overture_conf=None, fsq_closed=None):
    ov = None if overture_conf is None else pd.DataFrame({
        "name": ["Test Cafe"], "lat": [LAT], "lon": [LON], "operating_status": [None],
        "confidence": [overture_conf], "version": [pd.Timestamp("2026-09-23")]})
    fsq = None if fsq_closed is None else pd.DataFrame({
        "name": ["Test Cafe"], "lat": [LAT], "lon": [LON], "date_closed": [pd.Timestamp(fsq_closed)],
        "date_refreshed": [pd.NaT]})
    return _Sources(pd.DataFrame(), pd.DataFrame(), None, ov, fsq, None)


BIZ = Business("Test Cafe", LAT, LON, dt.date(2023, 6, 1), dt.date(2023, 5, 31))


@pytest.mark.parametrize("fate, src, today, status", [
    # a closure recorded before the 18-month mark (Dec 2024)
    (_fate("2024-05-01", "vacant"), _src(0.95), TODAY, "closed"),
    # recorded after the mark, nothing showing it traded at the mark: can't tell
    (_fate("2025-06-01", "replaced", last_edit="2023-06-01"), _src(), TODAY, "unknown"),
    # recorded after the mark, but a mapper edited it as open after the mark
    (_fate("2025-06-01", "replaced", last_edit="2025-02-01"), _src(), TODAY, "survived"),
    # still on the map and confirmed by a confident listing after the mark
    (_fate(last_edit="2023-06-01"), _src(0.9), TODAY, "survived"),
    # still on the map, only a weak listing: not strong enough
    (_fate(last_edit="2023-06-01"), _src(0.5), TODAY, "unknown"),
    # the mark hasn't arrived
    (_fate(last_edit="2023-06-01"), _src(), dt.date(2024, 6, 1), "censored"),
    # Foursquare says closed, but a mapper edited it as open later: sources disagree
    (_fate(last_edit="2025-02-01"), _src(fsq_closed="2024-01-01"), TODAY, "unknown"),
])
def test_horizon_status(fate, src, today, status):
    assert _horizon(BIZ, fate, None, src, today, BT.survival).status == status


def test_a_closure_carries_its_failure_type():
    h = _horizon(BIZ, _fate("2024-05-01", "replaced"), None, _src(), TODAY, BT.survival)
    assert (h.kind, h.failure, h.closed_on) == ("replaced", "operator", dt.date(2024, 5, 1))


def test_closure_by_third():
    pred = np.array([6, 5, 4, 3, 2, 1], float)
    status = np.array(["survived", "survived", "closed", "unknown", "closed", "closed"])
    failure = np.array(["", "", "site", "", "operator", "site"])
    rows = closure_by_third(pred, status, failure, np.array([0, 0, 1, 0, 2, 1], float))
    assert [(r["third"], r["judged"], r["closed"]) for r in rows] == [
        ("top", 2, 0), ("middle", 1, 1), ("bottom", 2, 2)]
    assert rows[2]["site_failures"] == 1 and rows[2]["operator_failures"] == 1
    assert rows[2]["closure_rate"] == 1.0 and rows[2]["mean_site_closures"] == 1.5
