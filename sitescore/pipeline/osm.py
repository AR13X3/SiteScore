"""OpenStreetMap via Overpass -> `pois`, one full snapshot per date.

Overpass can return the map as it was on a past date, so each snapshot is
genuinely historical (published_at = the snapshot date).
"""

from __future__ import annotations

import json

import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.mock_city import STATIONS
from sitescore.pipeline.mock_world import mock_world


class Osm(Adapter):
    source_id = "osm"
    tables = ("pois",)

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        world = mock_world(ctx)
        frames = []
        for kind, history in world.venues.values():
            for d in ctx.snapshot_dates:
                t = pd.Timestamp(d)
                open_ = history[(history["open"] <= t)
                                & (history["close"].isna() | (history["close"] > t))]
                frames.append(pd.DataFrame({
                    "osm_id": "mock:" + open_["venue_id"],
                    "name": open_["name"],
                    "lon": open_["lon"],
                    "lat": open_["lat"],
                    "tags": [_tags(kind.tags, n, b) for n, b in zip(open_["name"], open_["brand"],
                                                                  strict=True)],
                    "version": pd.Timestamp(d),
                }))
        for i, st in enumerate(STATIONS):
            extra = {"station": "light_rail"} if st.mode == "light_rail" else {}
            for d in ctx.snapshot_dates:
                if (st.opened and d < st.opened) or (st.closed and d >= st.closed):
                    continue
                frames.append(pd.DataFrame([{
                    "osm_id": f"mock:station-{i:02d}", "name": st.name, "lon": st.lon,
                    "lat": st.lat, "tags": _tags({"railway": "station", **extra}, st.name, None),
                    "version": pd.Timestamp(d),
                }]))
        df = pd.concat(frames, ignore_index=True)
        return {"pois": stamp(df, published_at=df["version"], valid_from=df["version"])}


def _tags(base: dict, name: str, brand: str | None) -> str:
    tags = {**base, "name": name}
    if brand:
        tags["brand"] = brand
    return json.dumps(tags, ensure_ascii=False)
