"""OpenStreetMap via Overpass -> `pois`, one full snapshot per date.

Overpass can return the map as it was on a past date ([date:"..."] attic
queries), so each snapshot is genuinely historical: published_at = the snapshot
date. Every tag any business profile cares about (competitors and anchors) is
fetched in one query per snapshot. Responses are cached per date, and a snapshot
that fails is skipped (the as-of view then falls back to the previous one).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time

import geopandas as gpd
import pandas as pd

from sitescore.config import load_business_types
from sitescore.pipeline import abs_geo
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import FetchError, cached_json, request
from sitescore.pipeline.mock_city import STATIONS
from sitescore.pipeline.mock_world import mock_world

log = logging.getLogger(__name__)

# Also fetched for every snapshot: stations (station-usage coordinates, anchors).
EXTRA_TAGS = [{"railway": "station"}, {"railway": "halt"}, {"railway": "tram_stop"}]


def tag_filters() -> list[dict[str, str]]:
    """Unique OSM tag filters across every business profile, plus stations."""
    seen, out = set(), []
    for profile in load_business_types().values():
        for rule in [*profile.competitors, *profile.anchors.items]:
            key = tuple(sorted(rule.tags.items()))
            if key not in seen:
                seen.add(key)
                out.append(dict(rule.tags))
    for tags in EXTRA_TAGS:
        if tuple(tags.items()) not in seen:
            out.append(tags)
    return out


def filter_statements(filters: list[dict[str, str]]) -> list[str]:
    """Overpass tag filters, merging single key=value rules per key into one regex.

    Fewer statements make historical ([date:]) queries much cheaper.
    """
    by_key: dict[str, set[str]] = {}
    other = []
    for tags in filters:
        if len(tags) == 1 and "*" not in tags.values():
            (k, v), = tags.items()
            by_key.setdefault(k, set()).add(v)
        else:
            other.append("".join(f'["{k}"]' if v == "*" else f'["{k}"="{v}"]'
                                 for k, v in tags.items()))
    merged = [f'["{k}"~"^({"|".join(sorted(vs))})$"]' for k, vs in sorted(by_key.items())]
    return merged + other


def overpass_query(bbox: tuple[float, float, float, float], date: dt.date | None) -> str:
    lon0, lat0, lon1, lat1 = bbox
    area = f"({lat0},{lon0},{lat1},{lon1})"
    parts = "".join(f"nwr{f}{area};" for f in filter_statements(tag_filters()))
    header = "[out:json][timeout:240]" + (f'[date:"{date.isoformat()}T00:00:00Z"]' if date else "")
    return f"{header};({parts});out center tags;"


class Osm(Adapter):
    source_id = "osm"
    tables = ("pois",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        extra = ctx.source(self.source_id).model_extra
        endpoints = list(extra["endpoints"])
        pause = float(extra.get("min_seconds_between_requests", 5))
        cooldown = float(extra.get("retry_cooldown_seconds", 90))
        window = extra.get("snapshots", {}).get("priority_window")
        bbox = _padded_bbox(ctx)

        frames: dict[dt.date, pd.DataFrame] = {}
        pending = prioritise(ctx.snapshot_dates, ctx.today, window)
        for attempt in (1, 2):
            failed = []
            for d in pending:
                path = ctx.raw_dir / "osm" / f"{ctx.region.id}_{d.isoformat()}.json"
                cached = path.exists()
                query = overpass_query(bbox, None if d == ctx.today else d)
                try:
                    data = cached_json(path, lambda q=query: _run(endpoints, q))
                except FetchError as exc:
                    log.warning("OSM snapshot %s failed (pass %d): %s", d, attempt, exc)
                    failed.append(d)
                    continue
                frames[d] = _elements_to_frame(data, d)
                if not cached:
                    log.info("OSM snapshot %s: %d elements", d, len(frames[d]))
                    time.sleep(pause)
            pending = failed
            if not pending:
                break
            if attempt == 1:
                log.info("OSM: %d snapshots failed; retrying after %.0fs", len(pending), cooldown)
                time.sleep(cooldown)
        if not frames:
            raise FetchError("every Overpass snapshot failed")
        if pending:
            log.warning("OSM: %d of %d snapshots missing (re-run to fill): %s", len(pending),
                        len(ctx.snapshot_dates), [str(d) for d in sorted(pending)])
        df = _within_study_area(ctx, pd.concat(frames.values(), ignore_index=True))
        return {"pois": stamp(df, published_at=df["version"], valid_from=df["version"])}

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


def prioritise(dates: list[dt.date], today: dt.date, window: list | None) -> list[dt.date]:
    """Today first, then dates inside the priority window, then the rest; newest first."""
    lo, hi = (pd.Timestamp(w).date() for w in window) if window else (today, today)

    def rank(d: dt.date) -> tuple[int, int]:
        group = 0 if d == today else 1 if lo <= d <= hi else 2
        return group, -d.toordinal()

    return sorted(dates, key=rank)


def _run(endpoints: list[str], query: str) -> dict:
    """Try each Overpass endpoint in turn (each with its own retries)."""
    last: Exception | None = None
    for url in endpoints:
        try:
            resp = request("POST", url, data={"data": query}, timeout=300, retries=1, backoff=30)
            data = resp.json()
            remark = data.get("remark", "")
            if "runtime error" in remark or "rate_limited" in remark:
                raise FetchError(f"{url}: {remark[:200]}")
            return data
        except (FetchError, ValueError) as exc:
            last = exc
            log.info("Overpass endpoint %s failed: %s", url, exc)
    raise FetchError(f"all Overpass endpoints failed: {last}")


def _padded_bbox(ctx: PipelineContext) -> tuple[float, float, float, float]:
    pad = ctx.region.buffer_m / 111_000 * 1.2
    lon0, lat0, lon1, lat1 = ctx.region.bbox
    return lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad


def _elements_to_frame(data: dict, snapshot: dt.date) -> pd.DataFrame:
    rows = []
    for e in data.get("elements", []):
        c = e.get("center") or e
        if "lat" not in c:
            continue
        tags = e.get("tags", {})
        rows.append({"osm_id": f"{e['type']}/{e['id']}", "name": tags.get("name", ""),
                     "lon": c["lon"], "lat": c["lat"],
                     "tags": json.dumps(tags, ensure_ascii=False)})
    df = pd.DataFrame(rows, columns=["osm_id", "name", "lon", "lat", "tags"])
    df["version"] = pd.Timestamp(snapshot)
    return df


def _within_study_area(ctx: PipelineContext, df: pd.DataFrame) -> pd.DataFrame:
    pts = gpd.GeoSeries(gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    inside = pts.to_crs(ctx.region.metric_crs).within(abs_geo.study_area(ctx))
    return df[inside.to_numpy()].reset_index(drop=True)


def _tags(base: dict, name: str, brand: str | None) -> str:
    tags = {**base, "name": name}
    if brand:
        tags["brand"] = brand
    return json.dumps(tags, ensure_ascii=False)
