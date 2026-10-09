"""Pipeline: mock adapters are valid and reproducible; failures fall back to mock."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pandas as pd
import pytest

from sitescore.datastore import TABLES, DataStore
from sitescore.datastore.store import validate_frame
from sitescore.pipeline import ADAPTERS, ensure_tables
from sitescore.pipeline import mock_world as mock_world_module
from sitescore.pipeline.base import Adapter, run_adapter


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda a: a.source_id)
def test_mock_output_matches_schema_and_region(adapter, ctx):
    lon_min, lat_min, lon_max, lat_max = ctx.region.bbox
    pad = 0.02  # degrees (~2 km) of slack
    for table, raw in adapter.mock(ctx).items():
        assert table in adapter.tables
        df = validate_frame(TABLES[table], raw)
        assert len(df) > 0
        if "lon" in df:  # every table but ASIC business names has coordinates
            assert df["lon"].between(lon_min - pad, lon_max + pad).all(), table
            assert df["lat"].between(lat_min - pad, lat_max + pad).all(), table
        assert (df["published_at"] <= pd.Timestamp(ctx.today)).all(), table


def test_mocks_are_reproducible(ctx):
    first = {a.source_id: a.mock(ctx) for a in ADAPTERS}
    mock_world_module._cache.clear()
    second = {a.source_id: a.mock(ctx) for a in ADAPTERS}
    for source, tables in first.items():
        for table, df in tables.items():
            pd.testing.assert_frame_equal(df, second[source][table], obj=f"{source}.{table}")


def test_places_describe_the_same_venues_as_osm(mock_store):
    """Every café/gym/childcare on today's map has an outcome record.

    (Not the reverse: a venue can open and close between two OSM snapshots.)
    """
    pois, places = mock_store.read("pois"), mock_store.read("places")
    today = pois[pois["version"] == pois["version"].max()]
    scored = today[today["tags"].str.contains('"cafe"|"fitness_centre"|"childcare"')]
    assert set(scored["osm_id"]) <= set(places["osm_id"])


class Broken(Adapter):
    source_id = "abs_census_wpp"
    tables = ("workers",)
    calls = 0

    def fetch(self, ctx):
        Broken.calls += 1
        raise ConnectionError("server down")

    def mock(self, ctx):
        return next(a for a in ADAPTERS if a.source_id == "abs_census_wpp").mock(ctx)


def test_failed_fetch_falls_back_to_mock(tmp_path, ctx):
    store = DataStore(tmp_path)
    [result] = run_adapter(Broken(), store, ctx)
    assert result.provenance == "mock"
    assert "ConnectionError: server down" in result.note
    assert store.provenance("workers") == "mock"


def test_offline_mode_never_fetches(tmp_path, ctx):
    offline = dataclasses.replace(ctx, settings=ctx.settings.model_copy(update={"offline": True}))
    Broken.calls = 0
    [result] = run_adapter(Broken(), DataStore(tmp_path), offline)
    assert Broken.calls == 0 and result.note == "offline mode"


def test_real_data_preferred_unless_forced_mock(tmp_path, ctx):
    frames = Broken().mock(ctx)
    store = DataStore(tmp_path)
    store.write("workers", frames["workers"], "mock")
    store.write("workers", frames["workers"].iloc[:10], "real")
    assert store.provenance("workers") == "real" and len(store.read("workers")) == 10
    assert DataStore(tmp_path, force_mock=True).provenance("workers") == "mock"


def test_ensure_tables_fills_only_gaps(tmp_path, ctx):
    store = DataStore(tmp_path)
    store.write("workers", Broken().mock(ctx)["workers"].iloc[:5], "real")
    results = ensure_tables(store, ctx, pack_dir=tmp_path / "no-pack")
    assert {r.table for r in results} == set(TABLES) - {"workers"}
    assert store.provenance("workers") == "real"


def test_station_months_only_exist_once_published(mock_store):
    su = mock_store.read("station_usage")
    assert su["published_at"].max() <= pd.Timestamp(dt.date(2026, 10, 9))
    # Carlingford heavy rail closed 5 Jan 2020 (January is a partial month).
    carl = su[su["station"] == "Carlingford"]
    assert carl["month"].max() == pd.Timestamp("2020-01-01")
    light_rail = su[su["station"] == "Carlingford Light Rail"]
    assert light_rail["month"].min() == pd.Timestamp("2024-12-01")
