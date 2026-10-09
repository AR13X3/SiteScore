"""The market as of a date: where customers are, and where competitors and anchors are.

Built once per (as-of date, business type) and shared by every candidate site.
Everything comes through the AsOfView, so the market is exactly what was knowable
on that date.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field, fields, replace

import numpy as np
import pandas as pd

from sitescore.config import BusinessProfile, ModelConfig, Region, TagRule
from sitescore.datastore import Access, AsOfView
from sitescore.features import FEATURES
from sitescore.model.geo import project


@dataclass(frozen=True)
class PointSet:
    """Demand points for one customer segment (projected metres)."""

    ids: np.ndarray
    x: np.ndarray
    y: np.ndarray
    people: np.ndarray

    def __len__(self) -> int:
        return len(self.ids)


@dataclass(frozen=True)
class Venues:
    """Competitors or anchors (projected metres)."""

    ids: np.ndarray
    names: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    x: np.ndarray
    y: np.ndarray
    weight: np.ndarray  # attractiveness for competitors, pull for anchors
    # Competitors only: True where the venue IS this business type (e.g. a café,
    # not a bakery that also sells coffee).
    primary: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.ids)

    def without(self, ids: set[str]) -> Venues:
        keep = ~np.isin(self.ids, list(ids))
        return Venues(*(None if getattr(self, f.name) is None else getattr(self, f.name)[keep]
                        for f in fields(self)))


@dataclass
class Market:
    as_of: dt.date
    business_type: str
    residents: PointSet
    resident_features: pd.DataFrame  # aligned with residents, one column per feature
    workers: PointSet
    commuters: PointSet
    competitors: Venues
    anchors: Venues
    # Census date: residents of developments finished before this are already counted.
    census_date: dt.date = dt.date(2021, 8, 10)
    # DAs approved as of the run date: da_id, x, y, new_dwellings, approved (Timestamp).
    developments: pd.DataFrame = field(default_factory=pd.DataFrame)
    data_used: list[Access] = field(default_factory=list)
    # Per-market memo for derived values (e.g. what a typical site looks like for rent).
    memo: dict = field(default_factory=dict, repr=False, compare=False)

    def segment(self, name: str) -> PointSet:
        return {"residents": self.residents, "workers": self.workers,
                "commuters": self.commuters}[name]

    def without(self, osm_ids: set[str]) -> Market:
        """The same market minus some venues, e.g. an existing café scored against its
        rivals but not itself (same as building it with exclude_osm_ids, but cheap)."""
        return replace(self, competitors=self.competitors.without(osm_ids),
                       anchors=self.anchors.without(osm_ids))


def build_market(view: AsOfView, profile: BusinessProfile, cfg: ModelConfig, region: Region,
                 exclude_osm_ids: tuple[str, ...] = ()) -> Market:
    """Assemble the market as of view.as_of.

    exclude_osm_ids: venues to leave out of the competitor set (in a backtest, the
    business being predicted must not compete with itself).
    """
    crs = region.metric_crs
    areas = view.table("areas")
    for feature in FEATURES:  # data processed before a feature existed: unknown, not an error
        if feature not in areas:
            areas = areas.assign(**{feature: np.nan})
    workers = view.table("workers")
    stations = view.table("station_usage")
    pois = view.table("pois")
    developments = _approved_developments(view.table("developments"), crs,
                                          cfg.developments.determined_approval_rate)

    people = areas["pop_total"].to_numpy(float)
    scale = profile.segments["residents"].population_scale
    if scale:
        people = people * areas[scale].to_numpy(float)

    competitors = _match_venues(pois, profile.competitors, crs, exclude_osm_ids)
    competitor_tags = competitors.pop("_tags")
    is_chain = np.array([is_branded(t) for t in competitor_tags])
    attract = np.where(is_chain, cfg.competitor_attractiveness.chain,
                       cfg.competitor_attractiveness.default)
    competitors_v = _venues(competitors, crs, competitors["_weight"].to_numpy() * attract)
    primary_rules = profile.primary_competitors
    competitors_v = replace(competitors_v, primary=np.array(
        [any(matches(t, r) for r in primary_rules) for t in competitor_tags], dtype=bool))
    anchors = _match_venues(pois, profile.anchors.items, crs, exclude_osm_ids)
    anchors.pop("_tags")

    return Market(
        as_of=view.as_of,
        business_type=profile.id,
        residents=_points(areas["sa1_code"], areas["lon"], areas["lat"], people, crs),
        resident_features=areas[list(FEATURES)].reset_index(drop=True),
        workers=_points(workers["point_id"], workers["lon"], workers["lat"],
                        workers["workers"].to_numpy(float), crs),
        commuters=_commuters(stations, cfg, crs),
        competitors=competitors_v,
        anchors=_venues(anchors, crs, anchors["_weight"].to_numpy()),
        census_date=areas["valid_from"].iat[0].date(),
        developments=developments,
        data_used=view.accessed,
    )


def _approved_developments(events: pd.DataFrame, crs: str, determined_rate: float
                           ) -> pd.DataFrame:
    """DAs whose latest known event is an approval (or a determination), with new dwellings.

    "determined" (outcome not published) counts at determined_rate. A project
    re-lodged as a new DA at the same spot is counted once: the latest known one.
    """
    cols = ["da_id", "x", "y", "new_dwellings", "approved"]
    if events.empty:
        return pd.DataFrame(columns=cols)
    latest = events.sort_values("event_date").groupby("da_id").tail(1)
    ok = latest[latest["event"].isin(["approved", "determined"]) & (latest["new_dwellings"] > 0)]
    x, y = project(ok["lon"], ok["lat"], crs)
    rate = np.where(ok["event"] == "determined", determined_rate, 1.0)
    df = pd.DataFrame({"da_id": ok["da_id"].to_numpy(), "x": x, "y": y,
                       "new_dwellings": ok["new_dwellings"].to_numpy(float) * rate,
                       "approved": ok["event_date"].to_numpy()})
    spot = (df["x"] / 10).round().astype(int).astype(str) + ":" + (df["y"] / 10).round().astype(int).astype(str)
    return df.loc[df.sort_values("approved").assign(spot=spot).drop_duplicates("spot", keep="last").index
                  ].reset_index(drop=True)


def _points(ids, lon, lat, people, crs) -> PointSet:
    x, y = project(lon, lat, crs)
    return PointSet(np.asarray(ids, dtype=str), x, y, np.asarray(people, dtype=float))


def _commuters(stations: pd.DataFrame, cfg: ModelConfig, crs: str) -> PointSet:
    """Regular commuters per station from the latest published months of patronage."""
    if stations.empty:
        return _points([], [], [], [], crs)
    latest = stations["month"].max()
    window_start = latest - pd.DateOffset(months=cfg.demand.station_usage_window_months - 1)
    recent = stations[stations["month"] >= window_start]
    # Stations with no data in the last 3 months have closed (e.g. converted to light rail).
    active = recent.groupby("station")["month"].max() >= latest - pd.DateOffset(months=2)
    recent = recent[recent["station"].isin(active[active].index)]
    per_station = recent.groupby("station").agg(
        lon=("lon", "first"), lat=("lat", "first"),
        monthly=("exits", "mean"), entries=("entries", "mean"))
    trips = (per_station["monthly"] + per_station["entries"]) / 2
    regulars = trips / cfg.demand.commuter_trips_per_month
    return _points(per_station.index, per_station["lon"], per_station["lat"],
                   regulars.to_numpy(), crs)


def is_branded(tags: dict) -> bool:
    """True for chain outlets (a non-empty OSM brand tag)."""
    brand = tags.get("brand")
    return isinstance(brand, str) and bool(brand.strip())


def matches(tags: dict, rule: TagRule) -> bool:
    return all(k in tags and (v == "*" or tags[k] == v) for k, v in rule.tags.items())


def _match_venues(pois: pd.DataFrame, rules: list[TagRule], crs: str,
                  exclude: tuple[str, ...]) -> dict:
    """POIs matching any rule; a POI matching several rules takes the highest weight."""
    keep, weights, tags_out = [], [], []
    for i, raw in enumerate(pois["tags"]):
        if pois["osm_id"].iat[i] in exclude:
            continue
        tags = json.loads(raw)
        w = max((r.weight for r in rules if matches(tags, r)), default=0.0)
        if w > 0:
            keep.append(i)
            weights.append(w)
            tags_out.append(tags)
    sub = pois.iloc[keep]
    return {"ids": sub["osm_id"].to_numpy(str), "names": sub["name"].fillna("").to_numpy(str),
            "lon": sub["lon"].to_numpy(float), "lat": sub["lat"].to_numpy(float),
            "_weight": pd.Series(weights, dtype=float), "_tags": tags_out}


def _venues(d: dict, crs: str, weight: np.ndarray) -> Venues:
    x, y = project(d["lon"], d["lat"], crs)
    return Venues(d["ids"], d["names"], d["lat"], d["lon"], x, y, np.asarray(weight, dtype=float))
