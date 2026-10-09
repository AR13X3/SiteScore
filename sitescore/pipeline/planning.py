"""NSW Planning Portal online DA data -> `developments` (one row per DA event).

A DA is stored as events (lodged, then determined/approved/refused), each
published on the day it happened. As of any date the model therefore sees only
what was known then: a DA determined in 2024 is just "lodged" in a 2023 run.

The real feed reports "Determined" without saying approved or refused, so those
events are recorded as "determined"; the model discounts them by an approval
rate (config: model.yaml developments.determined_approval_rate). Only original
Development Applications with new dwellings are kept (no modifications/CDCs).
"""

from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from sitescore.pipeline import abs_geo
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import cached_json, request
from sitescore.pipeline.mock_world import mock_world

log = logging.getLogger(__name__)

MOCK_FIRST_LODGED = dt.date(2019, 1, 1)
PAGE_SIZE = 1000


def fetch_applications(url: str, councils: list[str]) -> list[dict]:
    """Every application for the councils, following pagination."""
    apps, page, pages = [], 1, 1
    while page <= pages:
        resp = request("GET", url, headers={
            "PageSize": str(PAGE_SIZE), "PageNumber": str(page),
            "filters": json.dumps({"filters": {"CouncilName": councils,
                                               "ApplicationType": ["Development Application"]}}),
        })
        body = resp.json()
        apps += body.get("Application", [])
        pages = int(body.get("TotalPages") or 1)
        page += 1
    return apps


# The Portal fills missing dates with the Unix epoch (1970-01-01); anything this old is
# a placeholder, not a date (online DAs started decades later).
EARLIEST_REAL_DATE = "1990-01-01"


def first_date(*values: str | None) -> str | None:
    """The first value that is a real date (placeholders like 1970-01-01 skipped)."""
    for v in values:
        if v and str(v)[:10] >= EARLIEST_REAL_DATE:
            return v
    return None


def applications_to_events(apps: list[dict]) -> pd.DataFrame:
    rows = []
    for a in apps:
        dwellings = a.get("NumberOfNewDwellings") or 0
        locs = a.get("Location") or []
        if a.get("ApplicationType") != "Development Application" or dwellings <= 0 or not locs:
            continue
        try:
            lon, lat = float(locs[0]["X"]), float(locs[0]["Y"])
        except (KeyError, TypeError, ValueError):
            continue
        base = {"da_id": a["PlanningPortalApplicationNumber"], "lon": lon, "lat": lat,
                "new_dwellings": int(dwellings)}
        lodged = first_date(a.get("LodgementDate"), a.get("SubmissionDate"))
        if lodged:
            rows.append({**base, "event": "lodged", "event_date": lodged})
        determined = first_date(a.get("DeterminationDate"))
        if a.get("ApplicationStatus") == "Determined" and determined:
            rows.append({**base, "event": "determined", "event_date": determined})
    df = pd.DataFrame(rows, columns=["da_id", "lon", "lat", "new_dwellings", "event", "event_date"])
    df["event_date"] = pd.to_datetime(df["event_date"].str[:10], errors="coerce")
    return df.dropna(subset=["event_date"]).drop_duplicates(["da_id", "event"])


class PlanningDA(Adapter):
    source_id = "planning_da"
    tables = ("developments",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        url = ctx.source(self.source_id).model_extra["url"]
        councils = ctx.region.planning_portal["council_names"]
        path = ctx.raw_dir / self.source_id / f"{ctx.region.id}_{ctx.today.isoformat()}.json"
        apps = cached_json(path, lambda: fetch_applications(url, councils))
        df = applications_to_events(apps)
        df = df[df["event_date"] <= pd.Timestamp(ctx.today)]
        pts = abs_geo.gpd.GeoDataFrame(geometry=abs_geo.gpd.points_from_xy(df["lon"], df["lat"]),
                                       crs="EPSG:4326")
        df = df[abs_geo.in_study_area(ctx, pts).to_numpy()].reset_index(drop=True)
        log.info("planning: %d applications -> %d dwelling DA events", len(apps), len(df))
        return {"developments": stamp(df, published_at=df["event_date"],
                                      valid_from=df["event_date"])}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        city = mock_world(ctx).city
        rng = np.random.default_rng(ctx.seed("developments"))
        n = 420
        size = rng.choice(["small", "medium", "large", "tower"], n, p=[0.70, 0.20, 0.08, 0.02])
        dwellings = np.select(
            [size == "small", size == "medium", size == "large"],
            [rng.integers(1, 3, n), rng.integers(3, 31, n), rng.integers(31, 201, n)],
            rng.integers(201, 601, n),
        )
        # Bigger projects go where apartments already cluster.
        lat, lon = city.sample(n, rng, job_mix=0.0)
        big = dwellings > 30
        apt_lat, apt_lon = self._near_apartments(city, int(big.sum()), rng)
        lat[big], lon[big] = apt_lat, apt_lon

        span = (ctx.today - MOCK_FIRST_LODGED).days
        lodged = [MOCK_FIRST_LODGED + dt.timedelta(days=int(d)) for d in rng.uniform(0, span, n)]
        months_to_decide = 3 + 0.06 * dwellings ** 0.8 + rng.exponential(2.5, n)
        outcome = rng.choice(["approved", "refused"], n, p=[0.88, 0.12])

        rows = []
        for i in range(n):
            base = {"da_id": f"MOCK-PAN-{i:05d}", "lon": lon[i], "lat": lat[i],
                    "new_dwellings": int(dwellings[i])}
            rows.append({**base, "event": "lodged", "event_date": lodged[i]})
            decided = lodged[i] + dt.timedelta(days=int(months_to_decide[i] * 30.4))
            if decided <= ctx.today:
                rows.append({**base, "event": outcome[i], "event_date": decided})
        df = pd.DataFrame(rows)
        df["event_date"] = pd.to_datetime(df["event_date"])
        return {"developments": stamp(df, published_at=df["event_date"],
                                      valid_from=df["event_date"])}

    @staticmethod
    def _near_apartments(city, n: int, rng: np.random.Generator):
        lat, lon = city.sample(n * 6, rng, job_mix=0.3)
        w = city.density(lat, lon, "apartments") + 1e-6
        pick = rng.choice(lat.size, n, replace=False, p=w / w.sum())
        return lat[pick], lon[pick]
