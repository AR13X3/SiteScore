"""Backtest cohorts: which businesses to predict, where they are, and when they opened.

Two sources:
- a CSV you provide (backtests/cohorts/*.csv): name, opened, and lat/lon or address;
- discovery from OpenStreetMap history: a business is "new" when its OSM id
  first appears in a quarterly snapshot inside the configured window.

For each business we also fix the as-of date for its prediction: the last
moment before it existed in the data, and never before every model input was
public (otherwise the model can't run without peeking).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from sitescore.config import BacktestCfg, BusinessProfile
from sitescore.datastore import TABLES, DataStore
from sitescore.model.market import is_branded, matches
from sitescore.paths import ROOT
from sitescore.pipeline.geocode import search as geocode

COHORT_DIR = ROOT / "backtests" / "cohorts"


@dataclass(frozen=True)
class Business:
    name: str
    lat: float
    lon: float
    opened: dt.date             # best estimate of the opening date
    as_of: dt.date              # prediction uses only data published on or before this
    osm_id: str = ""            # excluded from its own competitor set
    address: str = ""
    source: str = "csv"         # csv | osm_first_mapped
    opened_note: str = ""       # e.g. "first mapped between 2023-04-01 and 2023-07-01"
    brand: str = ""


# --- Data readiness -------------------------------------------------------------------


def data_ready_date(store: DataStore) -> dt.date:
    """Earliest date on which every model input has at least one release."""
    earliest = []
    for name, spec in TABLES.items():
        if spec.model_visible and store.has(name):
            earliest.append(store.read(name)["published_at"].min().date())
    return max(earliest)


# --- CSV cohorts ----------------------------------------------------------------------


def _parse_date(value: str) -> dt.date:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}", value):
        value += "-15"  # month only: assume mid-month
    return dt.date.fromisoformat(value)


def load_csv(path: Path, ready: dt.date) -> list[Business]:
    """Rows need name, opened (YYYY-MM or YYYY-MM-DD) and lat+lon or address."""
    out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("name"):
                continue
            opened = _parse_date(row["opened"])
            lat, lon = row.get("lat"), row.get("lon")
            if not (lat and lon):
                hits = geocode(row.get("address", ""), 1)
                if not hits:
                    raise ValueError(f"{row['name']}: no lat/lon and address not found")
                lat, lon = hits[0]["lat"], hits[0]["lon"]
            out.append(Business(
                name=row["name"], lat=float(lat), lon=float(lon), opened=opened,
                as_of=max(opened - dt.timedelta(days=1), ready), osm_id=row.get("osm_id", ""),
                address=row.get("address", ""), source="csv",
                opened_note=row.get("notes", ""),
            ))
    return out


# --- Discovery from OSM history -------------------------------------------------------


def primary_rules(profile: BusinessProfile) -> list:
    """The profile's main competitor tags (highest weight), e.g. amenity=cafe."""
    top = max(r.weight for r in profile.competitors)
    return [r for r in profile.competitors if r.weight == top]


def discover_from_osm(store: DataStore, profile: BusinessProfile, cfg: BacktestCfg
                      ) -> list[Business]:
    pois = store.read("pois")
    rules = primary_rules(profile)
    tags = pois["tags"].map(json.loads)
    keep = tags.map(lambda t: any(matches(t, r) for r in rules))
    pois = pois[keep].assign(_tags=tags[keep])
    versions = sorted(pd.to_datetime(pois["version"].unique()))
    ready = data_ready_date(store)
    lo, hi = (pd.Timestamp(d) for d in cfg.window)

    first_seen = pois.sort_values("version").drop_duplicates("osm_id", keep="first")
    out = []
    for _, row in first_seen.iterrows():
        seen = row["version"]
        idx = versions.index(seen)
        if idx == 0:
            continue  # already there in the first snapshot: not a new opening
        before = versions[idx - 1]
        opened = before + (seen - before) / 2
        if not (lo <= opened <= hi) or not row["name"]:
            continue
        brand = row["_tags"].get("brand") if is_branded(row["_tags"]) else ""
        if brand and not cfg.include_chains:
            continue
        as_of = max(before.date(), ready)
        if as_of >= seen.date():
            continue  # no way to predict it without seeing it already exist
        out.append(Business(
            name=row["name"], lat=float(row["lat"]), lon=float(row["lon"]),
            opened=opened.date(), as_of=as_of, osm_id=row["osm_id"], source="osm_first_mapped",
            opened_note=f"first mapped between {before.date()} and {seen.date()}", brand=brand,
        ))
    return sorted(out, key=lambda b: b.opened)


# --- Linking a business to its OSM id -------------------------------------------------


def _name_tokens(name: str) -> set[str]:
    stop = {"cafe", "café", "coffee", "the", "and", "co", "&", "espresso", "kitchen", "bar"}
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in stop}


def link_osm_ids(businesses: list[Business], store: DataStore, max_m: float = 80) -> list[Business]:
    """Fill missing osm_ids by name match within max_m metres in any snapshot."""
    pois = store.read("pois").drop_duplicates("osm_id")
    out = []
    for b in businesses:
        if b.osm_id:
            out.append(b)
            continue
        d = np.hypot((pois["lon"] - b.lon) * 92_600, (pois["lat"] - b.lat) * 110_500)
        near = pois[d <= max_m]
        tokens = _name_tokens(b.name)
        same_name = [bool(tokens & _name_tokens(str(n))) for n in near["name"]]
        hits = near[same_name]
        out.append(replace(b, osm_id=str(hits["osm_id"].iloc[0])) if len(hits) else b)
    return out


def list_cohorts() -> list[str]:
    return sorted(p.stem for p in COHORT_DIR.glob("*.csv"))
