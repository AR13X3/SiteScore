"""OpenStreetMap element histories -> `poi_history` (outcome data, backtest only).

The quarterly snapshots in `pois` say whether a café was on the map on a date,
but only for the tags we query, so a café that became a vacant shop or a
sandwich bar simply vanishes. The OSM API keeps every version of every element,
with its date: from that the backtest learns when a business closed and what it
became. One request per element that was ever a scored business type in any
snapshot; responses are cached and refreshed after `cache_days`.

Each version is published the moment it's saved, so published_at = its timestamp.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time

import numpy as np
import pandas as pd

from sitescore.config import load_business_type
from sitescore.model.market import matches
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import FetchError, request
from sitescore.pipeline.mock_world import mock_world

log = logging.getLogger(__name__)

COLUMNS = ["osm_id", "seq", "name", "lon", "lat", "tags", "deleted", "changeset", "timestamp"]


class OsmHistory(Adapter):
    source_id = "osm_history"
    tables = ("poi_history",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        if ctx.store is None or not ctx.store.has("pois") or ctx.store.provenance("pois") != "real":
            raise RuntimeError("needs real OSM snapshots first (python run.py data --only osm)")
        extra = ctx.source(self.source_id).model_extra
        pois = ctx.store.read("pois")
        ids = tracked_ids(pois, extra["business_types"])
        centres = pois.drop_duplicates("osm_id", keep="last").set_index("osm_id")[["lon", "lat"]]
        pause, max_age = float(extra["min_seconds_between_requests"]), float(extra["cache_days"])
        frames, failed = [], []
        for i, osm_id in enumerate(ids):
            path = ctx.raw_dir / self.source_id / f"{osm_id.replace('/', '_')}.json"
            fresh = path.exists() and time.time() - path.stat().st_mtime < max_age * 86_400
            try:
                if not fresh:
                    url = extra["url"].format(element=osm_id)
                    data = request("GET", url, retries=2, backoff=5, timeout=60).json()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data), encoding="utf-8")
                    time.sleep(pause)
                data = json.loads(path.read_text(encoding="utf-8"))
            except (FetchError, ValueError) as exc:
                log.warning("OSM history %s failed: %s", osm_id, exc)
                failed.append(osm_id)
                continue
            frames.append(versions_frame(osm_id, data["elements"], centres.loc[osm_id]))
            if (i + 1) % 50 == 0:
                log.info("OSM history: %d / %d elements", i + 1, len(ids))
        if not frames:
            raise FetchError("no OSM element history could be fetched")
        if failed:
            log.warning("OSM history: %d of %d elements failed (re-run to fill)", len(failed),
                        len(ids))
        df = pd.concat(frames, ignore_index=True)
        return {"poi_history": _stamp(df)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        """The mock map's cafés: mapped when they open; at closure (plus a mapper's
        delay) deleted, tagged disused, or turned into another kind of business."""
        rng = np.random.default_rng(ctx.seed("osm_history"))
        kind, venues = mock_world(ctx).venues["cafe"]
        today = pd.Timestamp(ctx.today)
        rows = []
        for v in venues.itertuples():
            osm_id = f"mock:{v.venue_id}"
            tags = {**kind.tags, "name": v.name}
            if isinstance(v.brand, str) and v.brand:
                tags["brand"] = v.brand
            rows.append(_row(osm_id, 1, v, tags, v.open))
            if pd.isna(v.close):
                continue
            mapped = v.close + pd.Timedelta(days=int(rng.integers(0, 60)))
            if mapped > today:
                continue
            fate = rng.choice(["deleted", "vacant", "other_use"], p=[0.5, 0.25, 0.25])
            after = {"deleted": None, "vacant": {"disused:amenity": "cafe"},
                     "other_use": {"amenity": "restaurant", "name": f"{v.name} Thai"}}[fate]
            rows.append(_row(osm_id, 2, v, after or {}, mapped, deleted=after is None))
        return {"poi_history": _stamp(pd.DataFrame(rows, columns=COLUMNS))}


def tracked_ids(pois: pd.DataFrame, business_types: list[str]) -> list[str]:
    """Every element that matched a business type's main competitor tag in any snapshot."""
    rules = [r for bt in business_types for r in load_business_type(bt).primary_competitors]
    tags = pois["tags"].map(json.loads)
    hit = tags.map(lambda t: any(matches(t, r) for r in rules))
    return sorted(set(pois.loc[hit, "osm_id"]))


def versions_frame(osm_id: str, elements: list[dict], centre: pd.Series) -> pd.DataFrame:
    """One row per version. Ways and deleted versions have no coordinates of their
    own, so they take the element's position from the snapshots."""
    rows = []
    for e in elements:
        deleted = e.get("visible") is False
        tags = e.get("tags", {})
        rows.append({
            "osm_id": osm_id, "seq": int(e["version"]), "name": tags.get("name", ""),
            "lon": e.get("lon", centre["lon"]), "lat": e.get("lat", centre["lat"]),
            "tags": json.dumps(tags, ensure_ascii=False), "deleted": deleted,
            "changeset": int(e.get("changeset", 0)),
            "timestamp": pd.Timestamp(e["timestamp"]).tz_localize(None),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def _row(osm_id: str, seq: int, v, tags: dict, when, deleted: bool = False) -> dict:
    return {"osm_id": osm_id, "seq": seq, "name": tags.get("name", ""), "lon": v.lon,
            "lat": v.lat, "tags": json.dumps(tags, ensure_ascii=False), "deleted": deleted,
            "changeset": 0, "timestamp": pd.Timestamp(when)}


def _stamp(df: pd.DataFrame) -> pd.DataFrame:
    when = pd.to_datetime(df.pop("timestamp")).dt.floor("D")
    return stamp(df, published_at=when, valid_from=when)


def as_of_date(df: pd.DataFrame) -> dt.date | None:
    """Newest edit in the table: how up to date the histories are."""
    return None if df.empty else df["published_at"].max().date()
