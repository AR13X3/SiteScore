"""Google Places (optional) -> `places`: rating, review count, open/closed, as of today.

Outcome data. Ratings and review counts are only available as of the day we
fetch them, so this table is never visible to the model (TableSpec.model_visible
is False); the backtest scorer reads it after the predictions are made.

Real fetch: one Text Search (Places API New) per business seen on the real OSM
map since `track_from` (so businesses that have since closed are included),
biased to its location and accepted only if the name matches within 150 m.

Google bills every request, so three guards keep the count down:

- Answers are cached under data/raw/google_places/ inside the repo (gitignored),
  so every machine and sandbox reuses them. Google's terms limit storing content,
  so a cached answer older than `cache_days` is asked again.
- A ledger (ledger.json in that folder) counts every request ever sent. A run
  that would push the total past `max_requests` is refused before it sends one.
- If data/processed/places.real.parquet was fetched less than `cache_days` ago,
  nothing is fetched at all unless `python run.py data --force` is given.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import shutil
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from sitescore.config import load_business_types
from sitescore.matching import distance_m, normalise_name, same_business
from sitescore.model.market import matches
from sitescore.pipeline.base import Adapter, KeepExisting, PipelineContext, stamp
from sitescore.pipeline.http import request
from sitescore.pipeline.mock_world import mock_world

log = logging.getLogger(__name__)

# Business types whose venues we score in backtests.
SCORED_KINDS = ("cafe", "gym", "childcare")
TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
# All of these bill as one "Text Search Enterprise" request (rating and review count
# already need that tier), so the extra fields cost nothing more.
FIELD_MASK = ("places.id,places.displayName,places.location,places.rating,"
              "places.userRatingCount,places.businessStatus,places.formattedAddress,"
              "places.primaryType,places.types,places.priceLevel,places.regularOpeningHours,"
              "places.movedPlaceId")
MATCH_RADIUS_M = 150
EXACT_NAME_RADIUS_M = 250
# Same normalised name this close: one business (e.g. "Gloria Jean's" / "Gloria Jeans",
# or a café redrawn as a building), so one request serves both.
SAME_QUERY_M = 60
# Never more than this many requests in total, whatever the config says.
HARD_LIMIT = 400


class RequestLedger:
    """Every Google request ever sent, persisted next to the cache.

    reserve() is called before each request and saved at once, so a request that
    times out (and may still be billed) is counted too.
    """

    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = min(int(limit), HARD_LIMIT)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.total = int(data.get("total", 0))
        self.runs: list[dict] = data.get("runs", [])

    @property
    def remaining(self) -> int:
        return max(self.limit - self.total, 0)

    def check(self, needed: int) -> None:
        if needed > self.remaining:
            raise RuntimeError(
                f"Places: {needed} requests needed but only {self.remaining} of "
                f"{self.limit} left in {self.path} ({self.total} sent so far); refusing")

    def reserve(self, day: dt.date) -> None:
        self.check(1)
        self.total += 1
        if not self.runs or self.runs[-1]["date"] != day.isoformat():
            self.runs.append({"date": day.isoformat(), "requests": 0})
        self.runs[-1]["requests"] += 1
        self.save()

    def note(self, day: dt.date, requests: int, why: str) -> None:
        """Record requests made outside the ledger (e.g. found in an old cache)."""
        self.total += requests
        self.runs.append({"date": day.isoformat(), "requests": requests, "note": why})
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"limit": self.limit, "total": self.total,
                                   "runs": self.runs}, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def _near(lat: float, lon: float, p: dict) -> float:
    loc = p.get("location", {})
    return float(distance_m(lat, lon, loc.get("latitude", 0), loc.get("longitude", 0)))


def _gname(p: dict) -> str:
    return p.get("displayName", {}).get("text", "")


def best_match(name: str, lat: float, lon: float, places: list[dict],
               pool: list[dict] | None = None) -> dict | None:
    """The business's Google record, or None.

    1. Google's highest-ranked answer to its own query that is the same business
       within 150 m;
    2. else the nearest such place among every answer to any query (a place often
       turns up under a neighbour's query: "XA Expresso" answered "Koko n Beans");
    3. else a place with exactly the same name within 250 m (big buildings put the
       pin far from the map point: "Crunch Fitness Parramatta", 153 m).
    """
    for p in places:
        if _near(lat, lon, p) <= MATCH_RADIUS_M and same_business(name, _gname(p)):
            return p
    others = [p for p in (pool or []) if _near(lat, lon, p) <= EXACT_NAME_RADIUS_M]
    same = [p for p in others if _near(lat, lon, p) <= MATCH_RADIUS_M
            and same_business(name, _gname(p))]
    if same:
        return min(same, key=lambda p: _near(lat, lon, p))
    exact = [p for p in [*places, *others]
             if _near(lat, lon, p) <= EXACT_NAME_RADIUS_M
             and normalise_name(_gname(p)) == normalise_name(name)]
    return min(exact, key=lambda p: _near(lat, lon, p)) if exact else None


def google_weekly_hours(hours: dict | None) -> float | None:
    """Hours open per week from Google's regularOpeningHours periods."""
    periods = (hours or {}).get("periods")
    if not periods:
        return None
    total = 0.0
    for p in periods:
        start, end = p.get("open"), p.get("close")
        if start is None:
            continue
        if end is None:  # open 24 hours
            return 168.0
        a = start.get("day", 0) * 24 + start.get("hour", 0) + start.get("minute", 0) / 60
        b = end.get("day", 0) * 24 + end.get("hour", 0) + end.get("minute", 0) / 60
        total += (b - a) % 168
    return round(total, 2)


def businesses_to_look_up(pois: pd.DataFrame, since: dt.date) -> pd.DataFrame:
    """Distinct (osm_id, name) of scored business types on the map since `since`."""
    rules = [r for key in SCORED_KINDS for r in load_business_types()[key].competitors
             if r.weight == max(x.weight for x in load_business_types()[key].competitors)]
    recent = pois[pois["version"] >= pd.Timestamp(since)]
    keep = recent["tags"].map(lambda t: any(matches(json.loads(t), r) for r in rules))
    named = recent[keep & (recent["name"].fillna("") != "")]
    return named.sort_values("version").drop_duplicates(["osm_id", "name"], keep="last")


def cache_path(folder: Path, osm_id: str, name: str) -> Path:
    return folder / (re.sub(r"[^A-Za-z0-9]+", "_", f"{osm_id}_{name}") + ".json")


def plan(todo: pd.DataFrame, folder: Path, today: dt.date, max_age: dt.timedelta
         ) -> list[dict]:
    """One entry per business: its cache file and the request that answers it.

    Businesses with the same normalised name within SAME_QUERY_M share one request
    (the first one's). `fresh` says whether that request's cached answer is usable.
    """
    entries: list[dict] = []
    for _, b in todo.iterrows():
        path = cache_path(folder, b["osm_id"], b["name"])
        key = normalise_name(b["name"])
        shared = next((e for e in entries if e["key"] == key and e["source"] == e["path"]
                       and distance_m(b["lat"], b["lon"], e["lat"], e["lon"]) <= SAME_QUERY_M),
                      None)
        source = shared["path"] if shared else path
        fresh = False
        if source.exists():
            fetched = dt.date.fromisoformat(json.loads(source.read_text(encoding="utf-8"))["fetched"])
            fresh = today - fetched <= max_age
        entries.append({"osm_id": b["osm_id"], "name": b["name"], "lat": b["lat"],
                        "lon": b["lon"], "key": key, "path": path, "source": source,
                        "fresh": fresh})
    return entries


def _migrate_old_cache(old: Path, new: Path, ledger: RequestLedger, today: dt.date) -> None:
    """Move answers cached at the old machine-local location into the repo folder,
    counting each as one request the ledger hadn't seen."""
    if not old.is_dir() or old.resolve() == new.resolve():
        return
    moved = 0
    for f in old.glob("*.json"):
        if f.name != "ledger.json" and not (new / f.name).exists():
            new.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), new / f.name)
            moved += 1
    if moved:
        ledger.note(today, moved, f"answers moved from {old}")
        log.info("Places: moved %d cached answers from %s", moved, old)


class GooglePlaces(Adapter):
    source_id = "google_places"
    tables = ("places",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        extra = ctx.source(self.source_id).model_extra
        max_age = dt.timedelta(days=int(extra.get("cache_days", 30)))
        done = ctx.store.root / "places.real.parquet" if ctx.store is not None else None
        if done is not None and done.exists() and not ctx.force:
            fetched = pd.Timestamp(pd.read_parquet(done, columns=["version"])["version"].max()).date()
            if ctx.today - fetched < max_age:
                raise KeepExisting(f"kept: fetched {fetched}, under {max_age.days} days old "
                                   "(--force to refetch)")
        key = ctx.settings.google_places_api_key
        if not key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY not set")
        if ctx.store is None or ctx.store.provenance("pois") != "real":
            raise RuntimeError("needs the real OSM map first: run `python run.py data --only osm`")

        folder = ctx.repo_raw_dir / self.source_id
        ledger = RequestLedger(folder / "ledger.json", int(extra.get("max_requests", HARD_LIMIT)))
        _migrate_old_cache(ctx.raw_dir / self.source_id, folder, ledger, ctx.today)
        todo = businesses_to_look_up(ctx.store.read("pois"),
                                     pd.Timestamp(extra.get("track_from", "2022-01-01")).date())
        entries = plan(todo, folder, ctx.today, max_age)
        to_send = [e for e in entries if not e["fresh"] and e["source"] == e["path"]]
        log.info("Places: %d businesses, %d requests needed, %d of %d left in the ledger",
                 len(entries), len(to_send), ledger.remaining, ledger.limit)
        ledger.check(len(to_send))  # all or nothing: never a half-fetched table

        folder.mkdir(parents=True, exist_ok=True)
        for i, e in enumerate(to_send, 1):
            ledger.reserve(ctx.today)
            # One attempt only: every retry would be another billed request. A failure
            # stops the run; answers so far stay cached, so a re-run only sends the rest.
            try:
                resp = request("POST", TEXT_SEARCH, retries=0, timeout=30, headers={
                    "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK,
                }, json={
                    "textQuery": e["name"], "maxResultCount": 5,
                    "locationBias": {"circle": {"center": {"latitude": e["lat"],
                                                           "longitude": e["lon"]},
                                                "radius": float(MATCH_RADIUS_M)}},
                })
            except httpx.HTTPStatusError as exc:  # Google's error body never echoes the key
                raise RuntimeError(f"Places request {i} of {len(to_send)} failed: HTTP "
                                   f"{exc.response.status_code} {exc.response.text[:300]}") from None
            e["path"].write_text(json.dumps({"fetched": ctx.today.isoformat(),
                                             "query": e["name"],
                                             "places": resp.json().get("places", [])}),
                                 encoding="utf-8")
            if i % 50 == 0:
                log.info("Places: %d of %d requests sent", i, len(to_send))

        answers = {e["source"]: json.loads(e["source"].read_text(encoding="utf-8"))
                   for e in entries}
        pool = list({p["id"]: p for a in answers.values() for p in a["places"]
                     if "id" in p}.values())
        rows = []
        for e in entries:
            cached = answers[e["source"]]
            match = best_match(e["name"], e["lat"], e["lon"], cached["places"], pool)
            if match:
                loc = match["location"]
                rows.append({
                    "place_id": match["id"], "osm_id": e["osm_id"], "name": e["name"],
                    "lon": loc["longitude"], "lat": loc["latitude"],
                    "rating": match.get("rating", np.nan),
                    "review_count": match.get("userRatingCount", 0),
                    "business_status": match.get("businessStatus", ""),
                    "google_name": match.get("displayName", {}).get("text", ""),
                    "primary_type": match.get("primaryType", ""),
                    "price_level": match.get("priceLevel", ""),
                    "weekly_hours": google_weekly_hours(match.get("regularOpeningHours")),
                    "address": match.get("formattedAddress", ""),
                    "moved_place_id": match.get("movedPlaceId", ""),
                })
        log.info("Places: %d requests sent (%d in total), %d of %d businesses matched",
                 len(to_send), ledger.total, len(rows), len(entries))
        if not rows:
            raise RuntimeError("no businesses matched in Google Places")
        # Dated by the oldest answer used, so the 30-day rules count from it.
        fetched = pd.Timestamp(min(a["fetched"] for a in answers.values()))
        df = pd.DataFrame(rows)
        return {"places": stamp(df, published_at=fetched, valid_from=fetched, version=fetched)}

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
