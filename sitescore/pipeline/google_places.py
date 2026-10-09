"""Google Places (optional) -> `places`: rating, review count, open/closed, as of today.

Outcome data. Ratings and review counts are only available as of the day we
fetch them, so this table is never visible to the model (TableSpec.model_visible
is False); the backtest scorer reads it after the predictions are made.

Real fetch: one Text Search (Places API New) per business seen on the real OSM
map since `track_from` (so businesses that have since closed are included),
biased to its location and accepted only if the name matches within 150 m.
Answers are cached for `cache_days`, as Google's terms limit storing content.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

import numpy as np
import pandas as pd

from sitescore.config import load_business_types
from sitescore.model.market import matches
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import request
from sitescore.pipeline.mock_world import mock_world

log = logging.getLogger(__name__)

# Business types whose venues we score in backtests.
SCORED_KINDS = ("cafe", "gym", "childcare")
TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ("places.id,places.displayName,places.location,places.rating,"
              "places.userRatingCount,places.businessStatus")
MATCH_RADIUS_M = 150


def _tokens(name: str) -> set[str]:
    stop = {"cafe", "café", "coffee", "the", "and", "co", "espresso", "kitchen", "bar"}
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in stop} or {name.lower()}


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return float(np.hypot((lon2 - lon1) * 92_600, (lat2 - lat1) * 110_500))


def best_match(name: str, lat: float, lon: float, places: list[dict]) -> dict | None:
    """The result that shares a name word with the business and lies within 150 m."""
    want = _tokens(name)
    for p in places:
        loc = p.get("location", {})
        got = _tokens(p.get("displayName", {}).get("text", ""))
        near = _distance_m(lat, lon, loc.get("latitude", 0), loc.get("longitude", 0))
        if want & got and near <= MATCH_RADIUS_M:
            return p
    return None


def businesses_to_look_up(pois: pd.DataFrame, since: dt.date) -> pd.DataFrame:
    """Distinct (osm_id, name) of scored business types on the map since `since`."""
    rules = [r for key in SCORED_KINDS for r in load_business_types()[key].competitors
             if r.weight == max(x.weight for x in load_business_types()[key].competitors)]
    recent = pois[pois["version"] >= pd.Timestamp(since)]
    keep = recent["tags"].map(lambda t: any(matches(json.loads(t), r) for r in rules))
    named = recent[keep & (recent["name"].fillna("") != "")]
    return named.sort_values("version").drop_duplicates(["osm_id", "name"], keep="last")


class GooglePlaces(Adapter):
    source_id = "google_places"
    tables = ("places",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        key = ctx.settings.google_places_api_key
        if not key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY not set")
        if ctx.store is None or ctx.store.provenance("pois") != "real":
            raise RuntimeError("needs the real OSM map first: run `python run.py data --only osm`")
        extra = ctx.source(self.source_id).model_extra
        todo = businesses_to_look_up(ctx.store.read("pois"),
                                     pd.Timestamp(extra.get("track_from", "2022-01-01")).date())
        limit = int(extra.get("max_requests", 400))
        if len(todo) > limit:
            log.warning("Places: %d businesses, looking up the first %d (max_requests)",
                        len(todo), limit)
            todo = todo.head(limit)

        folder = ctx.raw_dir / self.source_id
        folder.mkdir(parents=True, exist_ok=True)
        max_age = dt.timedelta(days=int(extra.get("cache_days", 30)))
        rows, calls = [], 0
        for _, b in todo.iterrows():
            path = folder / (re.sub(r"[^A-Za-z0-9]+", "_", f"{b['osm_id']}_{b['name']}") + ".json")
            cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if cached is None or ctx.today - dt.date.fromisoformat(cached["fetched"]) > max_age:
                resp = request("POST", TEXT_SEARCH, retries=2, timeout=30, headers={
                    "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK,
                }, json={
                    "textQuery": b["name"], "maxResultCount": 3,
                    "locationBias": {"circle": {"center": {"latitude": b["lat"],
                                                           "longitude": b["lon"]},
                                                "radius": float(MATCH_RADIUS_M)}},
                })
                cached = {"fetched": ctx.today.isoformat(), "places": resp.json().get("places", [])}
                path.write_text(json.dumps(cached), encoding="utf-8")
                calls += 1
            match = best_match(b["name"], b["lat"], b["lon"], cached["places"])
            if match:
                loc = match["location"]
                rows.append({"place_id": match["id"], "osm_id": b["osm_id"], "name": b["name"],
                             "lon": loc["longitude"], "lat": loc["latitude"],
                             "rating": match.get("rating", np.nan),
                             "review_count": match.get("userRatingCount", 0),
                             "business_status": match.get("businessStatus", "")})
        log.info("Places: %d new requests, %d of %d businesses matched", calls, len(rows), len(todo))
        if not rows:
            raise RuntimeError("no businesses matched in Google Places")
        today = pd.Timestamp(ctx.today)
        return {"places": stamp(pd.DataFrame(rows), published_at=today, valid_from=today,
                                version=today)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        world = mock_world(ctx)
        rng = np.random.default_rng(ctx.seed("places"))
        today = pd.Timestamp(ctx.today)
        frames = []
        for key in SCORED_KINDS:
            _, h = world.venues[key]
            # Google keeps permanently closed places listed; drop ones closed long ago.
            h = h[h["close"].isna() | (h["close"] >= pd.Timestamp("2019-01-01"))]
            end = h["close"].fillna(today)
            # Reviews accrue while open; Google reviews only really took off ~2014.
            months_active = ((end - h["open"].clip(lower=pd.Timestamp("2014-01-01"))).dt.days
                             / 30.4).clip(lower=1)
            perf = h["performance"].to_numpy()
            rate = np.exp(0.9 + 0.6 * perf + rng.normal(0, 0.3, len(h)))  # reviews per month
            frames.append(pd.DataFrame({
                "place_id": "mock-place-" + h["venue_id"],
                "osm_id": "mock:" + h["venue_id"],
                "name": h["name"],
                "lon": h["lon"],
                "lat": h["lat"],
                "rating": np.clip(4.25 + 0.25 * perf + rng.normal(0, 0.2, len(h)), 2.5, 5.0).round(1),
                "review_count": rng.poisson(months_active.to_numpy() * rate),
                "business_status": np.where(h["close"].isna(), "OPERATIONAL", "CLOSED_PERMANENTLY"),
            }))
        df = pd.concat(frames, ignore_index=True)
        return {"places": stamp(df, published_at=today, valid_from=today, version=today)}
