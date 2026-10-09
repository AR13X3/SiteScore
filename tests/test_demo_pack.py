"""The committed demo pack: real tables restored on a fresh clone, never over your data."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from sitescore.datastore import TABLES, DataStore
from sitescore.pipeline import demo_pack, ensure_tables


def test_pack_round_trip_and_startup_restore(tmp_path, mock_store, ctx):
    source = DataStore(tmp_path / "source")
    for table in TABLES:
        source.write(table, mock_store.read(table), "real")  # pretend it was all fetched
    pack = tmp_path / "pack"
    made = demo_pack.make(source, pack, today=dt.date(2026, 10, 10))
    assert set(made["tables"]) == set(TABLES) - demo_pack.NEVER_PACKED
    assert not (pack / "places.parquet").exists()  # Google terms: never redistributed

    fresh = DataStore(tmp_path / "fresh")  # a fresh clone: no data at all
    results = ensure_tables(fresh, ctx, pack_dir=pack)
    assert {r.table for r in results if r.source_id == "demo_pack"} == set(made["tables"])
    assert fresh.provenance("pois") == "real" and fresh.provenance("places") == "mock"
    pd.testing.assert_frame_equal(fresh.read("pois"), source.read("pois"))
    assert "demo pack" in fresh.catalog()["pois"]["real"]["note"]


def test_restore_never_overwrites_existing_data(tmp_path, mock_store):
    source = DataStore(tmp_path / "source")
    source.write("pois", mock_store.read("pois"), "real")
    pack = tmp_path / "pack"
    demo_pack.make(source, pack)
    mine = DataStore(tmp_path / "mine")
    mine.write("pois", mock_store.read("pois").iloc[:10], "real")
    assert demo_pack.restore(mine, pack) == []
    assert len(mine.read("pois")) == 10
