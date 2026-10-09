"""Transport for NSW station entries/exits -> `station_usage` (station x month)."""

from __future__ import annotations

import datetime as dt
import logging
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from sitescore.pipeline import abs_geo
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import cached_json, download, request
from sitescore.pipeline.mock_city import STATIONS

log = logging.getLogger(__name__)

FIRST_MONTH = dt.date(2016, 7, 1)
# Typical monthly pattern of rail patronage (Jan..Dec): summer holidays dip.
_SEASON = np.array([0.82, 0.97, 1.04, 0.97, 1.04, 1.01, 1.0, 1.04, 1.02, 1.02, 1.04, 0.93])


def _covid_factor(month: dt.date) -> float:
    """Approximate shape of Sydney rail patronage through COVID (mock only)."""
    steps = [
        (dt.date(2020, 3, 1), 0.60), (dt.date(2020, 4, 1), 0.22), (dt.date(2020, 6, 1), 0.45),
        (dt.date(2020, 10, 1), 0.60), (dt.date(2021, 7, 1), 0.28), (dt.date(2021, 11, 1), 0.55),
        (dt.date(2022, 3, 1), 0.72), (dt.date(2023, 1, 1), 0.85), (dt.date(2024, 1, 1), 0.92),
    ]
    factor = 1.0
    for start, value in steps:
        if month >= start:
            factor = value
    return factor


SMALL_COUNT = 25  # TfNSW publishes counts under 50 as "Less than 50"
_DROP_WORDS = re.compile(r"\b(station|light rail|metro|stop|railway)\b")


def station_key(name: str) -> str:
    """'Parramatta  Station' / 'Parramatta' -> 'parramatta'; 'X Light Rail' -> 'x'."""
    s = _DROP_WORDS.sub(" ", str(name).lower())
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(s.split())


def parse_usage_csv(path) -> pd.DataFrame:
    """Normalise one TfNSW entries/exits file: station, month, direction, trips."""
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[["MonthYear", "Station", "Entry_Exit", "Trip"]].dropna()
    trips = df["Trip"].str.replace(",", "").str.strip()
    return pd.DataFrame({
        "station": df["Station"].str.split().str.join(" "),
        "month": pd.to_datetime(df["MonthYear"].str.strip().str[:7] + "-01"),
        # Files mix "Entry"/"Entries" and "Exit"/"Exits".
        "direction": np.where(df["Entry_Exit"].str.strip().str.lower().str.startswith("entr"),
                              "entry", "exit"),
        "trips": pd.to_numeric(trips.where(~trips.str.startswith("Less"), str(SMALL_COUNT)),
                               errors="coerce"),
    }).dropna()


class TfnswStations(Adapter):
    source_id = "tfnsw_station_usage"
    tables = ("station_usage",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        src = ctx.source(self.source_id)
        folder = ctx.raw_dir / self.source_id
        # Resources are listed oldest first; where months overlap, the newer file wins.
        files = [download(url, folder / url.rsplit("/", 1)[1]) for url in src.model_extra["resources"]]
        usage = pd.concat([parse_usage_csv(f) for f in files], ignore_index=True)
        usage = usage.drop_duplicates(["station", "month", "direction"], keep="last")
        wide = (usage.pivot_table(index=["station", "month"], columns="direction",
                                  values="trips", aggfunc="sum")
                .reset_index().rename(columns={"entry": "entries", "exit": "exits"}))

        locations = _station_locations(ctx)
        wide["key"] = wide["station"].map(station_key)
        df = wide.merge(locations, on="key", how="inner")
        if df.empty:
            raise RuntimeError("no TfNSW stations matched OSM station locations in the region")
        unmatched = sorted(set(locations["key"]) - set(wide["key"]))
        if unmatched:
            log.info("OSM stations with no TfNSW patronage: %s", unmatched)

        lag = pd.Timedelta(days=src.published_at.lag_days or 0)
        df = df[["station", "lon", "lat", "month", "entries", "exits"]].fillna(0)
        df = stamp(df, published_at=df["month"] + pd.offsets.MonthEnd(0) + lag,
                   valid_from=df["month"], valid_to=df["month"] + pd.offsets.MonthBegin(1))
        return {"station_usage": df[df["published_at"] <= pd.Timestamp(ctx.today)]}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        rng = np.random.default_rng(ctx.seed("station_usage"))
        lag = pd.Timedelta(days=ctx.source(self.source_id).published_at.lag_days or 0)
        months = pd.date_range(FIRST_MONTH, ctx.today, freq="MS")
        rows = []
        for st in STATIONS:
            for m in months:
                month = m.date()
                if (st.opened and month < st.opened.replace(day=1)) or (st.closed and month >= st.closed):
                    continue
                years = (month - FIRST_MONTH).days / 365.25
                level = (st.monthly_exits * _SEASON[month.month - 1] * _covid_factor(month)
                         * 1.012 ** years * rng.normal(1, 0.03))
                rows.append({"station": st.name, "lon": st.lon, "lat": st.lat, "month": m,
                             "exits": round(level), "entries": round(level * rng.normal(0.99, 0.01))})
        df = pd.DataFrame(rows)
        month_end = df["month"] + pd.offsets.MonthEnd(0)
        df = stamp(df, published_at=month_end + lag, valid_from=df["month"],
                   valid_to=df["month"] + pd.offsets.MonthBegin(1))
        # Months not yet published as of today don't exist yet.
        return {"station_usage": df[df["published_at"] <= pd.Timestamp(ctx.today)]}


def _station_locations(ctx: PipelineContext) -> pd.DataFrame:
    """Station coordinates from OSM (TfNSW patronage files have names only).

    Station positions don't change, so the current map is used for every month.
    """
    pad = ctx.region.buffer_m / 111_000 * 1.2
    lon0, lat0, lon1, lat1 = ctx.region.bbox
    area = f"({lat0 - pad},{lon0 - pad},{lat1 + pad},{lon1 + pad})"
    query = (f'[out:json][timeout:120];(nwr["railway"~"^(station|halt|tram_stop)$"]{area};'
             f'nwr["public_transport"="station"]{area};);out center tags;')
    endpoints = list(ctx.source("osm").model_extra["endpoints"])
    path = ctx.raw_dir / "tfnsw_station_usage" / f"{ctx.region.id}_station_locations.json"
    data = cached_json(path, lambda: request("POST", endpoints[0], data={"data": query},
                                             timeout=180).json())
    rows = []
    for e in data.get("elements", []):
        tags, c = e.get("tags", {}), e.get("center") or e
        if "name" in tags and "lat" in c:
            rows.append({"key": station_key(tags["name"]), "lon": c["lon"], "lat": c["lat"],
                         "rank": 0 if tags.get("railway") == "station" else 1})
    df = pd.DataFrame(rows, columns=["key", "lon", "lat", "rank"])
    df = df[df["key"] != ""].sort_values("rank").drop_duplicates("key")
    pts = gpd.GeoSeries(gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    inside = pts.to_crs(ctx.region.metric_crs).within(abs_geo.study_area(ctx)).to_numpy()
    return df[inside][["key", "lon", "lat"]].reset_index(drop=True)
