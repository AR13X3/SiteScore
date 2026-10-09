"""Parsers behind the real-data adapters, tested offline on small inline fixtures."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from sitescore.config import load_model_config
from sitescore.model.market import _approved_developments
from sitescore.pipeline.abs_census import fill_gaps
from sitescore.pipeline.abs_workers import spread_workers
from sitescore.pipeline.geocode import normalise_address
from sitescore.pipeline.osm import filter_statements
from sitescore.pipeline.planning import applications_to_events
from sitescore.pipeline.tfnsw import parse_usage_csv, station_key


@pytest.mark.parametrize("raw, key", [
    ("Parramatta  Station", "parramatta"),
    ("Parramatta", "parramatta"),
    ("Parramatta Square Light Rail", "parramatta square"),
    ("Paddy's Markets Light Rail", "paddys markets"),
    ("Epping Station", "epping"),
    ("Leppington  Station", "leppington"),
])
def test_station_key(raw, key):
    assert station_key(raw) == key


def test_parse_usage_csv_handles_every_published_format(tmp_path):
    f = tmp_path / "usage.csv"
    f.write_text(
        "MonthYear,Station,Station_Type ,Entry_Exit,Trip\n"
        "2016-07,Parramatta  Station,Train,Entry,\"1,000\"\n"
        "2024-10-01 00:00:00.000,Parramatta  Station,Train,Exits,Less than 50\n"
        "2024-10,Westmead Station,Train,Entries,12\n", encoding="utf-8")
    df = parse_usage_csv(f)
    assert list(df["direction"]) == ["entry", "exit", "entry"]
    assert list(df["trips"]) == [1000, 25, 12]
    assert list(df["month"].dt.strftime("%Y-%m")) == ["2016-07", "2024-10", "2024-10"]
    assert df["station"].iloc[0] == "Parramatta Station"


def _app(**kw) -> dict:
    base = {"PlanningPortalApplicationNumber": "PAN-1", "ApplicationType": "Development Application",
            "NumberOfNewDwellings": 10, "ApplicationStatus": "Determined",
            "LodgementDate": "2023-01-10", "DeterminationDate": "2023-09-01",
            "Location": [{"X": "151.0", "Y": "-33.8"}]}
    return {**base, **kw}


def test_planning_applications_become_dated_events():
    df = applications_to_events([
        _app(),
        _app(PlanningPortalApplicationNumber="PAN-2", ApplicationStatus="Under Assessment"),
        _app(PlanningPortalApplicationNumber="PAN-3", ApplicationType="Modification Application"),
        _app(PlanningPortalApplicationNumber="PAN-4", NumberOfNewDwellings=0),
        _app(PlanningPortalApplicationNumber="PAN-5", Location=[{"X": "null", "Y": "null"}]),
    ])
    assert sorted(zip(df["da_id"], df["event"], strict=True)) == [
        ("PAN-1", "determined"), ("PAN-1", "lodged"), ("PAN-2", "lodged")]
    assert df.loc[df["event"] == "determined", "event_date"].iloc[0] == pd.Timestamp("2023-09-01")


def _events(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["da_id", "lon", "lat", "new_dwellings", "event", "event_date"]
                        ).assign(event_date=lambda d: pd.to_datetime(d["event_date"]))


def test_determined_developments_discounted_and_relodged_projects_counted_once():
    rate = load_model_config().developments.determined_approval_rate
    events = _events([
        ("A", 151.0, -33.8, 100, "lodged", "2021-01-01"),
        ("A", 151.0, -33.8, 100, "determined", "2021-06-01"),
        ("B", 151.0, -33.8, 98, "determined", "2022-03-01"),   # same spot, re-lodged later
        ("C", 151.01, -33.81, 20, "approved", "2022-01-01"),
        ("D", 151.02, -33.82, 50, "lodged", "2022-01-01"),     # never determined: ignored
    ])
    df = _approved_developments(events, "EPSG:7856", rate)
    assert sorted(df["da_id"]) == ["B", "C"]
    assert df.set_index("da_id").loc["B", "new_dwellings"] == pytest.approx(98 * rate)
    assert df.set_index("da_id").loc["C", "new_dwellings"] == 20


def test_spread_workers_preserves_sa2_totals_and_follows_land_use():
    mb = pd.DataFrame({
        "sa2_code": ["S1", "S1", "S1", "S2", "S2"],
        "category": ["Commercial", "Residential", "Parkland", "Parkland", "Water"],
        "area_sqkm": [0.1, 1.0, 1.0, 0.5, 0.5],
    })
    density = {"Commercial": 1.0, "Residential": 0.02, "Parkland": 0.0, "Water": 0.0}
    w = spread_workers(mb, pd.Series({"S1": 1000.0, "S2": 50.0}), density)
    assert w[mb["sa2_code"] == "S1"].sum() == pytest.approx(1000)
    assert w.iloc[0] > w.iloc[1] and w.iloc[2] == 0
    assert w[mb["sa2_code"] == "S2"].sum() == pytest.approx(50)  # no weighted blocks: by area


def test_fill_gaps_uses_population_weighted_median():
    df = pd.DataFrame({"pop_total": [100, 300, 0], "median_income_personal_weekly": [500, 900, 0],
                       "age_0_4_share": [0.1, 0.2, np.nan]})
    out = fill_gaps(df, ["median_income_personal_weekly", "age_0_4_share"])
    assert out["median_income_personal_weekly"].iloc[2] == 900
    assert out["age_0_4_share"].iloc[2] == 0.2


def test_overpass_filters_are_merged_per_key():
    stmts = filter_statements([{"amenity": "cafe"}, {"amenity": "school"}, {"office": "*"},
                               {"amenity": "fast_food", "cuisine": "coffee_shop"}])
    assert stmts == ['["amenity"~"^(cafe|school)$"]', '["office"]',
                     '["amenity"="fast_food"]["cuisine"="coffee_shop"]']


@pytest.mark.parametrize("q, out", [
    ("20 George St, Parramatta NSW 2150", "20 GEORGE STREET PARRAMATTA"),
    ("3/12 Smith Pde Rydalmere", "3/12 SMITH PARADE RYDALMERE"),
    ("x' OR 1=1; --", "X OR 1 1 --"),
])
def test_address_normalisation_is_tidy_and_safe(q, out):
    assert normalise_address(q) == out
    assert "'" not in normalise_address(q)


def test_real_census_dates_from_config():
    """Real and mock Census rows carry the same publication dates (from sources.yaml)."""
    from sitescore.config import load_sources
    src = load_sources()
    assert src["abs_census_gcp"].published_at.date == dt.date(2022, 6, 28)
    assert src["abs_census_wpp"].published_at.date == dt.date(2022, 10, 12)
