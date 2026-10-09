"""Multi-source survival evidence: matching, voting, ageing, and each source's rules."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from sitescore.backtest.cohort import Business
from sitescore.backtest.outcomes import Evidence, _aged, _asic, _foursquare, _overture, _vote
from sitescore.matching import best_match, normalise_name, same_business

TODAY = dt.date(2026, 10, 10)
CAFE = Business("Two Deers Cafe", -33.8175, 151.0002, dt.date(2023, 2, 15), dt.date(2023, 1, 1))


@pytest.mark.parametrize("a, b, same", [
    ("XS", "XS Espresso", True),                 # name expanded
    ("Picollo Me", "Piccolo Me", True),          # typo fixed
    ("Nadia’s", "Nadias Cafe", True),            # punctuation / generic words
    ("Koko ‘n’ Beans", "XA Expresso", False),    # replaced by another business
    ("Mulberry Tree", "The Chai Nook", False),
])
def test_same_business(a, b, same):
    assert same_business(a, b) is same


def test_normalise_name():
    assert normalise_name("Nadia’s Café & Co.") == "nadias cafe co"


def test_best_match_needs_proximity_and_name():
    cands = pd.DataFrame({"name": ["Two Deers", "Two Deers", "Other"],
                          "lat": [-33.8175, -33.83, -33.8175], "lon": [151.0003, 151.0, 151.0002]})
    m = best_match(CAFE.name, CAFE.lat, CAFE.lon, cands)
    assert m is not None and m["lat"] == -33.8175
    assert best_match("Nowhere Cafe", CAFE.lat, CAFE.lon, cands) is None


def test_vote_and_ageing():
    fresh = Evidence("osm", False, 2.0, "replaced", TODAY)
    stale = Evidence("foursquare", True, 1.0, "listed", TODAY - dt.timedelta(days=365))
    aged = _aged(stale, TODAY, half_life_months=12)
    assert aged.weight == pytest.approx(0.5, rel=0.02)
    still_open, score = _vote([fresh, aged])
    assert still_open is False and score == pytest.approx((0.5 - 2.0) / 2.5, rel=0.01)
    assert _vote([]) == (None, None)


def _frame(**cols) -> pd.DataFrame:
    return pd.DataFrame({k: [v] for k, v in cols.items()})


def test_overture_rules():
    release = pd.Timestamp("2026-09-23")
    listed = _frame(name="Two Deers", lat=CAFE.lat, lon=CAFE.lon, operating_status=None,
                    confidence=0.9, version=release)
    e = _overture(CAFE, listed, 1.0)
    assert e.open and e.weight == pytest.approx(0.9)
    low = listed.assign(confidence=0.3)
    assert not _overture(CAFE, low, 1.0).open
    missing = listed.assign(name="Someone Else")
    e = _overture(CAFE, missing, 1.0)
    assert not e.open and e.weight == pytest.approx(0.4)
    too_new = Business("New", CAFE.lat, CAFE.lon, dt.date(2026, 8, 1), dt.date(2026, 7, 1))
    assert _overture(too_new, listed, 1.0) is None


def test_foursquare_rules():
    snap = pd.Timestamp("2025-02-06")
    base = {"name": "Two Deers Cafe", "lat": CAFE.lat, "lon": CAFE.lon,
            "date_refreshed": pd.Timestamp("2025-01-20"), "version": snap}
    assert _foursquare(CAFE, _frame(**base, date_closed=pd.NaT), 1.0).open
    closed = _foursquare(CAFE, _frame(**base, date_closed=pd.Timestamp("2024-06-01")), 1.0)
    assert not closed.open and closed.as_of == dt.date(2024, 6, 1)
    # A closure before this business opened belongs to a previous tenant.
    assert _foursquare(CAFE, _frame(**base, date_closed=pd.Timestamp("2020-01-01")), 1.0) is None
    late = Business("Late", CAFE.lat, CAFE.lon, dt.date(2025, 1, 1), dt.date(2024, 12, 31))
    assert _foursquare(late, _frame(**base, date_closed=pd.NaT), 1.0) is None


def test_asic_only_trusts_a_unique_name_registered_around_opening():
    version = pd.Timestamp(TODAY)

    def names(*rows):
        return pd.DataFrame([{"bn_name": n, "status": s, "registered": pd.Timestamp(r),
                              "cancelled": pd.Timestamp(c) if c else pd.NaT, "abn": "1",
                              "version": version} for n, s, r, c in rows])

    ok = names(("TWO DEERS CAFE", "Registered", "2022-04-21", None))
    assert _asic(CAFE, ok, 0.75, (18, 6)).open
    gone = names(("TWO DEERS CAFE", "Deregistered", "2022-04-21", "2025-03-01"))
    assert not _asic(CAFE, gone, 0.75, (18, 6)).open
    old = names(("TWO DEERS CAFE", "Registered", "2015-01-01", None))       # outside window
    assert _asic(CAFE, old, 0.75, (18, 6)) is None
    twice = names(("TWO DEERS CAFE", "Registered", "2022-04-21", None),
                  ("TWO DEERS CAFE", "Registered", "2022-09-01", None))   # ambiguous
    assert _asic(CAFE, twice, 0.75, (18, 6)) is None
