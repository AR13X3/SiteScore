"""Backtest: cohort discovery, no-leakage predictions, outcomes and accuracy metrics."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sitescore.backtest.predict as predict_module
from sitescore.backtest import backtest, load_cohort
from sitescore.backtest.cohort import Business, data_ready_date, load_csv
from sitescore.backtest.metrics import pairwise_accuracy, spearman, survival_auc
from sitescore.backtest.outcomes import observe, weekly_hours
from sitescore.backtest.predict import predict
from sitescore.config import (
    load_backtest_config,
    load_business_type,
    load_calendar,
    load_model_config,
    load_region,
)
from sitescore.datastore import DataStore, LeakageError

TODAY = dt.date(2026, 10, 9)
CAFE, CFG, REGION = load_business_type("cafe"), load_model_config(), load_region()
CAL, BT = load_calendar(REGION.state), load_backtest_config()


@pytest.fixture(scope="module")
def cohort(mock_store):
    return load_cohort("osm", mock_store)


@pytest.fixture(scope="module")
def result(mock_store):
    return backtest("osm", mock_store, today=TODAY)


# --- Cohort -------------------------------------------------------------------------


def test_discovered_businesses_are_new_in_the_window_and_predictable(cohort, mock_store):
    ready = data_ready_date(mock_store)
    pois = mock_store.read("pois")
    assert len(cohort) >= 10
    for b in cohort:
        assert BT.window[0] <= b.opened <= BT.window[1]
        assert b.as_of >= ready
        first_seen = pois.loc[pois["osm_id"] == b.osm_id, "version"].min().date()
        assert b.as_of < first_seen  # predicted before it ever appears in the data


def test_csv_cohort_with_coordinates(tmp_path, mock_store):
    f = tmp_path / "demo.csv"
    f.write_text("name,opened,lat,lon\nTest Café,2023-05,-33.815,151.0035\n", encoding="utf-8")
    [b] = load_csv(f, data_ready_date(mock_store))
    assert b.opened == dt.date(2023, 5, 15) and b.as_of == dt.date(2023, 5, 14)


# --- No leakage ---------------------------------------------------------------------


def test_every_prediction_uses_only_data_published_by_its_as_of_date(result):
    assert result.rows
    for row in result.rows:
        assert row.data_cutoff is not None and row.data_cutoff <= row.as_of


def test_future_data_cannot_change_predictions(cohort, mock_store, tmp_path):
    """Plant later-published records, including the business itself: nothing changes."""
    sample = cohort[:4]
    before = [predict(b, mock_store, CAFE, CFG, REGION, CAL, BT.score_months).score
              for b in sample]

    store = DataStore(tmp_path / "planted")
    shutil.copytree(mock_store.root, store.root)
    pois = store.read("pois")
    future = pd.Timestamp("2030-01-01")
    planted = pd.DataFrame([{
        "osm_id": f"future:{i}", "name": "Future Café", "lon": b.lon, "lat": b.lat,
        "tags": json.dumps({"amenity": "cafe", "name": "Future Café"}),
        "version": future, "published_at": future, "valid_from": future, "valid_to": pd.NaT,
    } for i, b in enumerate(sample)])
    store.write("pois", pd.concat([pois, planted], ignore_index=True), "mock")

    after = [predict(b, store, CAFE, CFG, REGION, CAL, BT.score_months).score for b in sample]
    assert after == before


def test_business_is_not_its_own_competitor(cohort, mock_store):
    b = cohort[0]
    # Pretend we only "discovered" it after it was already on the map.
    late = dataclasses.replace(b, as_of=TODAY)
    p = predict(late, mock_store, CAFE, CFG, REGION, CAL, BT.score_months)
    assert p.score > 0  # ran without LeakageError: excluded from the competitor set


def test_leakage_check_fires_on_a_bad_cutoff(cohort, mock_store, monkeypatch):
    real_build = predict_module.build_market

    def leaky_build(view, *args, **kwargs):
        market = real_build(view, *args, **kwargs)
        stamp = dataclasses.replace(market.data_used[0],
                                    latest_published=view.as_of + dt.timedelta(days=1))
        market.data_used = [stamp, *market.data_used[1:]]
        return market

    monkeypatch.setattr(predict_module, "build_market", leaky_build)
    with pytest.raises(LeakageError):
        predict(cohort[0], mock_store, CAFE, CFG, REGION, CAL, BT.score_months)


def test_prediction_code_never_touches_outcome_data():
    source = Path(predict_module.__file__).read_text(encoding="utf-8")
    assert "outcomes" not in source and not re.search(r"['\"]places['\"]", source)


# --- Outcomes and metrics -----------------------------------------------------------


@pytest.mark.parametrize("spec, hours", [
    ("Mo-Fr 07:00-19:00; Sa 09:00-19:00; Su,PH 09:00-18:00", 79.0),
    ("Tu-Sa 07:00-15:00, Su 08:00-15:00", 47.0),
    ("Fr-We 05:30-12:30, Th 05:30-13:00", 49.5),
    ("Mo-Fr 07:00-15:00; Su off", 40.0),
    ("07:30-17:00", 66.5),
    ("24/7", 168.0),
    ("sunrise-sunset", None),
])
def test_weekly_hours(spec, hours):
    assert weekly_hours(spec) == hours


def test_closed_and_renamed_businesses_count_as_not_surviving(mock_store):
    pois = mock_store.read("pois")
    latest = pois[pois["version"] == pois["version"].max()].iloc[0]
    gone = Business("Gone Café", -33.8, 151.0, dt.date(2023, 1, 1), dt.date(2022, 12, 31),
                    osm_id="mock:never-existed")
    renamed = Business("Old Name", latest["lat"], latest["lon"], dt.date(2023, 1, 1),
                       dt.date(2022, 12, 31), osm_id=latest["osm_id"])
    out = observe([gone, renamed], mock_store, TODAY)
    gone_out = out["mock:never-existed"]
    # Not on the map and not listed anywhere: only a weak "not in Overture" vote.
    assert [e.source for e in gone_out.evidence] == ["overture"]
    assert gone_out.still_open is False and gone_out.survival_score == -1.0
    assert out[latest["osm_id"]].still_open is False


def test_mock_reviews_are_not_matched_to_real_map_data(mock_store, tmp_path):
    store = DataStore(tmp_path / "mixed")
    shutil.copytree(mock_store.root, store.root)
    store.write("pois", mock_store.read("pois"), "real")  # pretend the map is real now
    pois = store.read("pois")
    row = pois[pois["version"] == pois["version"].max()].iloc[0]
    b = Business(row["name"], row["lat"], row["lon"], dt.date(2023, 1, 1), dt.date(2022, 12, 31),
                 osm_id=row["osm_id"])
    assert observe([b], store, TODAY)[row["osm_id"]].reviews is None


def test_metrics():
    assert pairwise_accuracy([3, 2, 1], [30, 20, 10]) == (1.0, 3)
    assert pairwise_accuracy([1, 2, 3], [30, 20, 10]) == (0.0, 3)
    assert pairwise_accuracy([1, 1], [2, 1]) == (0.5, 1)
    assert survival_auc([5, 4, 1], [True, True, False]) == 1.0
    assert survival_auc([1, 2], [True, True]) is None
    assert spearman(np.array([1, 2]), np.array([1, 2])) is None


def test_backtest_result_is_complete(result):
    a = result.accuracy
    assert a.n == len(result.rows) > 0
    assert 0 <= a.pairwise_accuracy <= 1 and a.pairs > 0
    assert sorted(r.predicted_rank for r in result.rows) == list(range(1, a.n + 1))
    assert result.caveats and result.provenance["pois"] == "mock"
