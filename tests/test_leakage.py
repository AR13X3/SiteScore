"""The no-leakage rule: a run as of date D never sees data published after D."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from sitescore.datastore import TABLES, DataStore, LeakageError, NoDataAsOf, SchemaError
from sitescore.datastore.store import validate_frame


def frame(table: str, n: int = 3, **cols) -> pd.DataFrame:
    """A minimal valid frame for `table`; override any column via kwargs."""
    spec = TABLES[table]
    base = {c: [0.0] * n for c in spec.required_columns}
    base.update({"valid_to": [pd.NaT] * n})
    base.update(cols)
    return pd.DataFrame(base)


def census(version: str, published: str, n: int = 3) -> pd.DataFrame:
    return frame("areas", n, sa1_code=[f"{version}-{i}" for i in range(n)],
                 version=[version] * n, valid_from=[version] * n, published_at=[published] * n)


@pytest.fixture
def store(tmp_path) -> DataStore:
    return DataStore(tmp_path)


def test_latest_table_uses_newest_release_published_by_date(store):
    store.write("areas", pd.concat([census("2016-08-09", "2017-06-27"),
                                    census("2021-08-10", "2022-06-28")]), "mock")
    # Census 2021 describes Aug 2021 but wasn't public until 28 June 2022.
    early = store.as_of(dt.date(2022, 1, 1)).table("areas")
    assert set(early["version"].dt.date) == {dt.date(2016, 8, 9)}
    late = store.as_of(dt.date(2022, 6, 28)).table("areas")
    assert set(late["version"].dt.date) == {dt.date(2021, 8, 10)}


def test_no_release_yet_raises(store):
    store.write("areas", census("2021-08-10", "2022-06-28"), "mock")
    with pytest.raises(NoDataAsOf, match="earliest available: 2022-06-28"):
        store.as_of(dt.date(2022, 6, 27)).table("areas")


def test_cumulative_table_hides_unpublished_months(store):
    months = pd.date_range("2024-01-01", "2024-04-01", freq="MS")
    published = months + pd.offsets.MonthEnd(0) + pd.Timedelta(days=45)
    store.write("station_usage", frame("station_usage", len(months), station=["P"] * 4,
                                       month=months, valid_from=months,
                                       published_at=published), "mock")
    # March 2024 is published mid-May, so at the end of April only Jan and Feb are known.
    seen = store.as_of(dt.date(2024, 4, 30)).table("station_usage")
    assert list(seen["month"].dt.month) == [1, 2]


def test_development_events_only_known_after_they_happen(store):
    events = frame("developments", 2, da_id=["DA1", "DA1"], event=["lodged", "approved"],
                   event_date=["2023-01-10", "2023-09-01"],
                   valid_from=["2023-01-10", "2023-09-01"],
                   published_at=["2023-01-10", "2023-09-01"])
    store.write("developments", events, "mock")
    assert list(store.as_of(dt.date(2023, 6, 1)).table("developments")["event"]) == ["lodged"]
    assert len(store.as_of(dt.date(2023, 9, 1)).table("developments")) == 2


def test_outcome_data_is_never_visible_to_the_model(mock_store):
    with pytest.raises(LeakageError, match="outcome data"):
        mock_store.as_of(dt.date(2030, 1, 1)).table("places")


def test_census_release_dates_respected_in_mock_data(mock_store):
    view = mock_store.as_of(dt.date(2022, 8, 1))
    assert len(view.table("areas")) > 0          # resident data: released 28 Jun 2022
    with pytest.raises(NoDataAsOf):              # employment data: released 12 Oct 2022
        view.table("workers")


def test_random_dates_never_leak(mock_store):
    """Property test: for many random as-of dates, nothing published later gets through."""
    rng = np.random.default_rng(0)
    start, end = dt.date(2016, 1, 1), dt.date(2026, 10, 9)
    for offset in rng.integers(0, (end - start).days, 150):
        as_of = start + dt.timedelta(days=int(offset))
        view = mock_store.as_of(as_of)
        for name, spec in TABLES.items():
            if not spec.model_visible:
                continue
            try:
                df = view.table(name)
            except NoDataAsOf:
                continue
            cutoff = pd.Timestamp(as_of)
            assert (df["published_at"] <= cutoff).all(), (name, as_of)
            assert (df["valid_from"] <= cutoff).all(), (name, as_of)
            if spec.kind == "latest":
                assert df["version"].nunique() <= 1, (name, as_of)


def test_access_log_records_what_was_used(mock_store):
    view = mock_store.as_of(dt.date(2023, 3, 1))
    view.table("pois")
    view.table("areas")
    log = {a.table: a for a in view.accessed}
    assert log["pois"].provenance == "mock"
    assert log["pois"].latest_published <= dt.date(2023, 3, 1)
    assert log["areas"].version == dt.date(2021, 8, 10)


@pytest.mark.parametrize("bad, message", [
    ({"published_at": [None, "2022-01-01", "2022-01-01"]}, "needs published_at"),
    ({"published_at": ["2020-01-01"] * 3, "valid_from": ["2021-01-01"] * 3}, "published before"),
])
def test_store_rejects_badly_dated_rows(bad, message):
    df = census("2021-08-10", "2022-06-28")
    for col, values in bad.items():
        df[col] = values
    with pytest.raises(SchemaError, match=message):
        validate_frame(TABLES["areas"], df)


def test_store_rejects_missing_columns():
    with pytest.raises(SchemaError, match="missing columns"):
        validate_frame(TABLES["workers"], pd.DataFrame({"lon": [1.0]}))
