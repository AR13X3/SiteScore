"""Every mapped business's life: when it appeared, whether and how it ended.

A *run* is one business on one OpenStreetMap element: an element that was
"Steaming Mug" and later "Four Cups" holds two runs. Runs come from element
histories (`poi_history`, every edit with its date) where available, otherwise
from the quarterly snapshots (`pois`).

How a run ends (`kind`):
    replaced   another café took over the spot: renamed in place to a different
               business, or deleted while a different café appeared within
               site_radius_m around that time. Operator failure; the site may be fine.
    vacant     tagged disused/vacant. Site failure.
    other_use  retagged as another kind of business. Site failure (for this type).
    removed    deleted with no successor seen: closed, what followed is unknown.

Not endings: name corrections ('Picollo Me' -> 'Piccolo Me'), a retag that keeps
the same business, and re-mapping (deleted, and the same business mapped again
nearby, e.g. a point redrawn as a building outline); a re-mapped run continues as
the new element (`continued_as`).

The date of an ending is the edit that recorded it, so the real closure happened
on or before it. Outcome data only: nothing here is a model input.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sitescore.config import BusinessProfile, SurvivalCfg
from sitescore.datastore import DataStore
from sitescore.matching import distance_m, same_business
from sitescore.model.market import is_branded, matches

MAIN_KEYS = ("amenity", "shop", "office", "craft", "leisure", "healthcare", "tourism", "club")
LIFECYCLE_PREFIXES = ("disused:", "was:", "abandoned:", "vacant:", "demolished:", "razed:",
                      "closed:")
COLUMNS = ["run_id", "osm_id", "name", "lat", "lon", "opened", "known_before", "first_snapshot",
           "last_edit", "checked", "closed", "kind", "detail", "successor", "continued_as",
           "prior_same_business", "predecessor", "brand", "source"]


@dataclass(frozen=True)
class Fate:
    """A business's run, following re-mappings to the element it continued as."""

    run_id: str
    closed: pd.Timestamp | None
    kind: str | None
    detail: str
    successor: str
    last_edit: pd.Timestamp | None   # newest edit while it was still this business
    checked: pd.Timestamp | None     # newest check_date / survey:date a mapper set
    on_map_today: bool


def build(store: DataStore, profile: BusinessProfile, cfg: SurvivalCfg) -> pd.DataFrame:
    """One row per run of every element that was ever this business type."""
    pois = store.read("pois")
    rules = profile.primary_competitors
    snaps = sorted(pois["version"].unique())
    is_biz = pois["tags"].map(lambda t: any(matches(json.loads(t), r) for r in rules))
    ids = sorted(set(pois.loc[is_biz, "osm_id"]))
    history = _history(store)
    groups = history.groupby("osm_id") if history is not None else None
    by_id = pois[pois["osm_id"].isin(ids)].sort_values("version").groupby("osm_id")

    runs: list[dict] = []
    for osm_id in ids:
        snap = by_id.get_group(osm_id)
        if groups is not None and osm_id in groups.groups:
            runs += _runs_from_history(osm_id, groups.get_group(osm_id), snap, rules)
        else:
            runs += _runs_from_snapshots(osm_id, snap, snaps, is_biz)
    df = pd.DataFrame(runs, columns=COLUMNS)
    return _resolve_deletions(df, cfg)


def fate(lifecycles: pd.DataFrame, run_id: str, max_hops: int = 3) -> Fate | None:
    """What became of a run, following re-mappings (same business, new element)."""
    rows = lifecycles.set_index("run_id")
    if run_id not in rows.index:
        return None
    r = rows.loc[run_id]
    last_edit, checked = r["last_edit"], r["checked"]
    for _ in range(max_hops):
        nxt = r["continued_as"]
        if not nxt or nxt not in rows.index:
            break
        r = rows.loc[nxt]
        last_edit = _latest(last_edit, r["last_edit"])
        checked = _latest(checked, r["checked"])
    closed = r["closed"] if pd.notna(r["closed"]) else None
    return Fate(str(r.name), closed, r["kind"] or None, r["detail"], r["successor"],
                _ts(last_edit), _ts(checked), closed is None)


def run_for(lifecycles: pd.DataFrame, osm_id: str, name: str, when: dt.date) -> str | None:
    """The run of this element that is this business (by name), nearest to `when`."""
    runs = lifecycles[lifecycles["osm_id"] == osm_id]
    if runs.empty:
        return None
    named = runs[_mask(same_business(n, name) for n in runs["name"])] if name else runs
    pick = named if len(named) else runs
    gap = (pick["opened"].fillna(pd.Timestamp("1900-01-01")) - pd.Timestamp(when)).abs()
    return str(pick.loc[gap.idxmin(), "run_id"])


def site_closures(lifecycles: pd.DataFrame, lat: float, lon: float, radius_m: float
                  ) -> pd.DataFrame:
    """Runs at this spot that ended (re-mappings excluded), oldest first."""
    d = distance_m(lat, lon, lifecycles["lat"].to_numpy(float), lifecycles["lon"].to_numpy(float))
    here = lifecycles[(d <= radius_m) & lifecycles["closed"].notna()]
    return here.sort_values("closed")


def failure_type(kind: str | None) -> str | None:
    return {"replaced": "operator", "vacant": "site", "other_use": "site",
            "removed": "unknown"}.get(kind or "")


# --- Runs from element histories ----------------------------------------------------------


def _runs_from_history(osm_id: str, versions: pd.DataFrame, snap: pd.DataFrame, rules
                       ) -> list[dict]:
    runs: list[dict] = []
    current: dict | None = None
    earlier_names: list[str] = []   # names this element had before the current run
    for v in versions.sort_values("seq").itertuples():
        when = pd.Timestamp(v.published_at)
        if v.deleted:
            if current:
                _end(current, when, "deleted", "deleted from OpenStreetMap")
                runs.append(current)
                current = None
            continue
        tags = json.loads(v.tags)
        name = v.name or ""
        biz = any(matches(tags, r) for r in rules)
        if current is None:
            if biz:
                current = _start(osm_id, len(runs), name, v, when, snap, earlier_names)
            elif name:
                earlier_names.append(name)
            continue
        if biz:
            if name and current["name"] and not same_business(name, current["name"]):
                _end(current, when, "replaced", f"renamed to '{name}' on OpenStreetMap", name)
                runs.append(current)
                earlier_names.append(current["name"])
                current = _start(osm_id, len(runs), name, v, when, snap, earlier_names)
                continue
            current["name"] = name or current["name"]   # corrections keep the run going
            _touch(current, when, tags)
        elif _vacant(tags):
            _end(current, when, "vacant", "tagged disused/vacant on OpenStreetMap")
            runs.append(current)
            earlier_names.append(current["name"])
            current = None
        elif name and current["name"] and same_business(name, current["name"]):
            _touch(current, when, tags)                 # same business, retagged
        elif any(k in tags for k in MAIN_KEYS):
            what = next(f"{k}={tags[k]}" for k in MAIN_KEYS if k in tags)
            _end(current, when, "other_use",
                 f"became {what}" + (f" '{name}'" if name else "") + " on OpenStreetMap")
            runs.append(current)
            earlier_names += [current["name"], name]
            current = None
        else:
            _end(current, when, "deleted", "business tags removed on OpenStreetMap")
            runs.append(current)
            current = None
    if current:
        runs.append(current)
    return runs


def _start(osm_id: str, n: int, name: str, v, when: pd.Timestamp, snap: pd.DataFrame,
           earlier_names: list[str]) -> dict:
    later = snap.loc[snap["version"] >= when, "version"]
    return {
        "run_id": f"{osm_id}#{n}", "osm_id": osm_id, "name": name, "lat": float(v.lat),
        "lon": float(v.lon), "opened": when, "known_before": when - pd.Timedelta(days=1),
        "first_snapshot": later.min() if len(later) else pd.NaT, "last_edit": when,
        "checked": _check_date(json.loads(v.tags)), "closed": pd.NaT, "kind": "",
        "detail": "", "successor": "", "continued_as": "",
        "prior_same_business": any(same_business(n_, name) for n_ in earlier_names if n_ and name),
        "predecessor": next((n_ for n_ in reversed(earlier_names)
                             if n_ and not same_business(n_, name)), ""),
        "brand": _brand(json.loads(v.tags)), "source": "history",
    }


def _touch(run: dict, when: pd.Timestamp, tags: dict) -> None:
    run["last_edit"] = when
    run["checked"] = _latest(run["checked"], _check_date(tags))


def _end(run: dict, when: pd.Timestamp, kind: str, detail: str, successor: str = "") -> None:
    run.update(closed=when, kind=kind, detail=detail, successor=successor)


def _brand(tags: dict) -> str:
    return tags["brand"] if is_branded(tags) else ""


def _vacant(tags: dict) -> bool:
    return (tags.get("shop") == "vacant" or tags.get("amenity") == "vacant"
            or any(k.startswith(LIFECYCLE_PREFIXES) for k in tags))


def _check_date(tags: dict) -> pd.Timestamp | None:
    dates = [pd.to_datetime(tags[k], errors="coerce") for k in tags
             if k in ("check_date", "survey:date", "survey_date") or k.startswith("check_date:")]
    dates = [d for d in dates if pd.notna(d)]
    return max(dates) if dates else None


# --- Runs from snapshots (no history available) ------------------------------------------


def _runs_from_snapshots(osm_id: str, snap: pd.DataFrame, snaps: list, is_biz: pd.Series
                         ) -> list[dict]:
    snap = snap[is_biz.loc[snap.index]]
    runs: list[dict] = []
    current: dict | None = None
    for row in snap.itertuples():
        name = row.name or ""
        if current and name and current["name"] and not same_business(name, current["name"]):
            _end(current, row.version, "replaced", f"now '{name}' on OpenStreetMap", name)
            runs.append(current)
            current = None
        if current is None:
            current = _start_snapshot(osm_id, len(runs), row, snaps)
            current["predecessor"] = runs[-1]["name"] if runs else ""
        current["name"] = name or current["name"]
    last_seen = snap["version"].max()
    if current and last_seen < snaps[-1]:
        gone = snaps[snaps.index(last_seen) + 1]
        _end(current, pd.Timestamp(gone), "deleted", "no longer on OpenStreetMap")
    if current:
        runs.append(current)
    return runs


def _start_snapshot(osm_id: str, n: int, row, snaps: list) -> dict:
    seen = pd.Timestamp(row.version)
    i = snaps.index(row.version)
    before = pd.Timestamp(snaps[i - 1]) if i else pd.NaT
    return {
        "run_id": f"{osm_id}#{n}", "osm_id": osm_id, "name": row.name or "",
        "lat": float(row.lat), "lon": float(row.lon),
        "opened": before + (seen - before) / 2 if i else pd.NaT, "known_before": before,
        "first_snapshot": seen, "last_edit": None, "checked": None, "closed": pd.NaT,
        "kind": "", "detail": "", "successor": "", "continued_as": "",
        "prior_same_business": False, "predecessor": "", "brand": _brand(json.loads(row.tags)),
        "source": "snapshots",
    }


# --- Deleted runs: re-mapped, replaced, or removed? --------------------------------------


def _resolve_deletions(df: pd.DataFrame, cfg: SurvivalCfg) -> pd.DataFrame:
    df = df.copy()
    remap_window = pd.DateOffset(months=cfg.remap_window_months)
    succ_window = pd.DateOffset(months=cfg.successor_window_months)
    lat, lon = df["lat"].to_numpy(float), df["lon"].to_numpy(float)
    for i in np.flatnonzero((df["kind"] == "deleted").to_numpy()):
        r = df.iloc[i]
        d = distance_m(r["lat"], r["lon"], lat, lon)
        others = df[(df["osm_id"] != r["osm_id"]) & (d <= cfg.remap_radius_m)]
        start = others["opened"].fillna(others["first_snapshot"])
        near_in_time = others[(start >= r["closed"] - remap_window)
                              & (start <= r["closed"] + remap_window)]
        same = near_in_time[_mask(same_business(n, r["name"]) for n in near_in_time["name"])]
        if len(same):
            df.loc[df.index[i], ["closed", "kind", "detail", "continued_as"]] = [
                pd.NaT, "", f"re-mapped as {same['osm_id'].iloc[0]}", same["run_id"].iloc[0]]
            continue
        spot = others[d[others.index] <= cfg.site_radius_m] if len(others) else others
        start = spot["opened"].fillna(spot["first_snapshot"])
        succ = spot[((start >= r["closed"] - succ_window) & (start <= r["closed"] + succ_window))
                    .to_numpy(bool) & _mask(not same_business(n, r["name"]) for n in spot["name"])]
        if len(succ):
            name = succ["name"].iloc[0] or "an unnamed café"
            df.loc[df.index[i], ["kind", "detail", "successor"]] = [
                "replaced", f"{r['detail']}; '{name}' opened at the same spot", name]
            if not df.at[succ.index[0], "predecessor"]:
                df.at[succ.index[0], "predecessor"] = r["name"]
        else:
            df.loc[df.index[i], "kind"] = "removed"
    for col in ("opened", "known_before", "first_snapshot", "closed"):
        df[col] = pd.to_datetime(df[col])
    return df


def _history(store: DataStore) -> pd.DataFrame | None:
    """Element histories, only when they describe the same world as the snapshots."""
    if not store.has("poi_history") or store.provenance("poi_history") != store.provenance("pois"):
        return None
    return store.read("poi_history")


def _mask(flags) -> np.ndarray:
    """Boolean row mask from a generator (an empty list would select columns instead)."""
    return np.fromiter(flags, dtype=bool)


def _latest(a, b):
    vals = [x for x in (a, b) if x is not None and pd.notna(x)]
    return max(vals) if vals else None


def _ts(x) -> pd.Timestamp | None:
    return None if x is None or pd.isna(x) else pd.Timestamp(x)
