"""Was a business that first appeared on the map really new?

OpenStreetMap only says when a business was *mapped*. In Parramatta the map's
café count tripled between 2019 and 2026, mostly because mappers caught up, so
many "first mapped" cafés are old businesses. Each discovered business gets a
verdict, from the strongest evidence available:

    remapped    the same business was already on the map nearby (a duplicate or
                redrawn element, or the same element retagged, e.g. bakery -> café)
    new         it took over from another business at the spot (strong), or
                Foursquare added it / its exact name was registered with ASIC around
                the opening
    older       Foursquare knew it long before it was mapped (ASIC can't say this:
                it has no addresses, and an older same-named business may be another
                outlet or another town)
    unverified  no other source either way, or the sources disagree

This reads outcome-only tables (Foursquare, ASIC), so the runner applies it after
every prediction is made. It decides which businesses count, never what the model
predicted for them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sitescore.backtest.cohort import Business
from sitescore.backtest.lifecycle import run_for
from sitescore.config import BacktestCfg
from sitescore.datastore import DataStore
from sitescore.matching import best_match, distance_m, normalise_name, same_business


@dataclass(frozen=True)
class OpeningCheck:
    verdict: str   # new | unverified | older | remapped
    detail: str


def check_openings(businesses: list[Business], store: DataStore, lifecycles: pd.DataFrame,
                   cfg: BacktestCfg) -> dict[str, OpeningCheck]:
    """Verdict per business, keyed like outcomes (osm_id or name)."""
    world = store.provenance("pois")

    def table(name: str) -> pd.DataFrame | None:
        ok = store.has(name) and store.provenance(name) == world
        return store.read(name) if ok else None

    fsq, names = table("fsq_places"), table("business_names")
    return {b.osm_id or b.name: check(b, lifecycles, fsq, names, cfg) for b in businesses}


def check(b: Business, lc: pd.DataFrame, fsq: pd.DataFrame | None, names: pd.DataFrame | None,
          cfg: BacktestCfg) -> OpeningCheck:
    s, oc = cfg.survival, cfg.opening_check
    opened = pd.Timestamp(b.opened)
    run_id = run_for(lc, b.osm_id, b.name, b.opened) if b.osm_id else None
    run = lc.set_index("run_id").loc[run_id] if run_id else None

    # 1. Already on the map: same element retagged, or another element redrawn.
    if run is not None and run["prior_same_business"]:
        return OpeningCheck("remapped", "the same business was on this map element before "
                                        "under other tags")
    if run_id and (lc["continued_as"] == run_id).any():
        src = lc.loc[lc["continued_as"] == run_id, "osm_id"].iloc[0]
        return OpeningCheck("remapped", f"redrawn from {src}, already on the map")
    earlier = _same_business_nearby_before(b, lc, run_id, s.remap_radius_m)
    if earlier:
        return OpeningCheck("remapped", earlier)

    # 2. Took over from another business at the same spot: a real opening.
    if run is not None and run["predecessor"]:
        return OpeningCheck("new", f"took over from '{run['predecessor']}'")
    window = pd.DateOffset(months=s.successor_window_months)
    d = distance_m(b.lat, b.lon, lc["lat"].to_numpy(float), lc["lon"].to_numpy(float))
    gone = lc[(d <= s.site_radius_m) & (lc["closed"] >= opened - window)
              & (lc["closed"] <= opened + window) & (lc["osm_id"] != b.osm_id)]
    if len(gone):
        return OpeningCheck("new", f"replaced '{gone['name'].iloc[0]}' "
                                   f"(closed {gone['closed'].iloc[0].date()})")

    # 3. Foursquare and ASIC: when did anyone first see it?
    votes: list[tuple[str, str]] = []
    m = best_match(b.name, b.lat, b.lon, fsq, max_m=150) if fsq is not None else None
    if m is not None and pd.notna(m["date_created"]):
        created = pd.Timestamp(m["date_created"])
        old = created < opened - pd.DateOffset(months=oc.fsq_created_months_before)
        votes.append(("older" if old else "new", f"Foursquare added it {created.date()}"))
    reg = _asic_registered(b.name, names)
    lo, hi = cfg.asic_match_window_months
    if reg is not None and opened - pd.DateOffset(months=lo) <= reg <= opened + pd.DateOffset(months=hi):
        votes.append(("new", f"ASIC name registered {reg.date()}"))
    said = {v for v, _ in votes}
    detail = "; ".join(t for _, t in votes)
    if said == {"older"}:
        return OpeningCheck("older", detail)
    if said == {"new"}:
        return OpeningCheck("new", detail)
    if said:
        return OpeningCheck("unverified", f"sources disagree: {detail}")
    return OpeningCheck("unverified", "no other source knows when it opened")


def _same_business_nearby_before(b: Business, lc: pd.DataFrame, run_id: str | None,
                                 radius_m: float) -> str:
    """Another element, same business, on the map before this one appeared and still there."""
    start = pd.Timestamp(b.opened)
    if run_id:
        row = lc.set_index("run_id").loc[run_id]
        start = row["opened"] if pd.notna(row["opened"]) else row["first_snapshot"]
    d = distance_m(b.lat, b.lon, lc["lat"].to_numpy(float), lc["lon"].to_numpy(float))
    others = lc[(d <= radius_m) & (lc["osm_id"] != b.osm_id)]
    began = others["opened"].fillna(others["first_snapshot"])
    alive = others["closed"].isna() | (others["closed"] >= start - pd.DateOffset(months=1))
    hit = others[(began < start).to_numpy(bool) & alive.to_numpy(bool)
                 & np.fromiter((same_business(n, b.name) for n in others["name"]), dtype=bool)]
    if hit.empty:
        return ""
    r = hit.iloc[0]
    since = r["opened"] if pd.notna(r["opened"]) else r["first_snapshot"]
    return f"already mapped as {r['osm_id']} since {pd.Timestamp(since).date()}"


def _asic_registered(name: str, names: pd.DataFrame | None) -> pd.Timestamp | None:
    """Registration date of a unique exact business name (ASIC has no addresses)."""
    if names is None:
        return None
    same = names[names["bn_name"].map(normalise_name) == normalise_name(name)]
    if len(same) != 1 or pd.isna(same["registered"].iloc[0]):
        return None
    return pd.Timestamp(same["registered"].iloc[0])
