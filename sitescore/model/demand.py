"""Layer 1: demand. Potential customers within walking distance of a site.

For each segment (residents, workers, commuters):

    potential customers = people within the segment's walking catchment
                          x participation (share who use this kind of business)
                          x time alignment (are they around when the business trades?)

Anchor tenants (supermarkets, stations...) near the site add a capped boost.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sitescore.config import SEGMENTS, BusinessProfile, ModelConfig
from sitescore.model.geo import minutes_to_metres, walk_distance
from sitescore.model.market import Market


@dataclass(frozen=True)
class Catchment:
    """Demand points reachable from a site, all segments stacked into flat arrays."""

    segment: np.ndarray        # segment name per point
    source_index: np.ndarray   # row in that segment's PointSet
    x: np.ndarray
    y: np.ndarray
    dist_m: np.ndarray         # walking distance to the site
    people: np.ndarray         # people at this point, after the soft catchment edge
    weight: np.ndarray         # potential customers at this point
    visits_per_month: np.ndarray
    fit_applies: np.ndarray    # bool


@dataclass(frozen=True)
class DemandResult:
    catchment: Catchment
    potential_customers: float
    by_segment: dict[str, dict]
    anchor_factor: float
    anchors_nearby: list[dict]


def time_alignment(profile: BusinessProfile) -> dict[str, float]:
    """Share of the business's trade that happens while each segment is around (0..1)."""
    weekday = 1 - profile.weekend_trade_share
    out = {}
    for seg in SEGMENTS:
        during_week = sum(d.trade_share * d.presence[seg] for d in profile.dayparts)
        out[seg] = weekday * during_week + profile.weekend_trade_share * profile.weekend_presence[seg]
    return out


def anchor_boost(sx: float, sy: float, market: Market, profile: BusinessProfile,
                 cfg: ModelConfig) -> tuple[float, list[dict]]:
    a = market.anchors
    if not len(a):
        return 1.0, []
    dist = walk_distance(sx, sy, a.x, a.y, cfg.distance, floor=False)
    near = dist <= profile.anchors.radius_m
    w = float(a.weight[near].sum())
    boost = profile.anchors.max_boost * w / (w + profile.anchors.half_saturation)
    order = np.argsort(dist[near])
    listed = [{"name": str(a.names[near][i]) or "unnamed", "distance_m": round(float(dist[near][i])),
               "weight": float(a.weight[near][i]), "lat": float(a.lat[near][i]),
               "lon": float(a.lon[near][i])} for i in order]
    return 1.0 + boost, listed


def reach(dist: np.ndarray, radius: float, fade: float) -> np.ndarray:
    """1 well inside the walk limit, fading linearly to 0 just beyond it."""
    if fade == 0:
        return (dist <= radius).astype(float)
    return np.clip((radius * (1 + fade) - dist) / (2 * fade * radius), 0.0, 1.0)


def compute_demand(sx: float, sy: float, market: Market, profile: BusinessProfile,
                   cfg: ModelConfig) -> DemandResult:
    tau = time_alignment(profile)
    cols: dict[str, list[np.ndarray]] = {k: [] for k in Catchment.__dataclass_fields__}
    by_segment = {}
    for seg in SEGMENTS:
        pts = market.segment(seg)
        spec = profile.segments[seg]
        radius = minutes_to_metres(spec.max_walk_minutes, cfg.distance)
        dist = walk_distance(sx, sy, pts.x, pts.y, cfg.distance)
        r = reach(dist, radius, cfg.distance.catchment_fade)
        idx = np.flatnonzero((r > 0) & (pts.people > 0))
        in_reach = pts.people[idx] * r[idx]
        weight = in_reach * spec.participation * tau[seg]
        for key, values in {
            "segment": np.full(len(idx), seg), "source_index": idx,
            "x": pts.x[idx], "y": pts.y[idx], "dist_m": dist[idx], "people": in_reach,
            "weight": weight, "visits_per_month": np.full(len(idx), spec.visits_per_month),
            "fit_applies": np.full(len(idx), spec.fit_applies),
        }.items():
            cols[key].append(values)
        by_segment[seg] = {
            "people_in_reach": float(in_reach.sum()),
            "participation": spec.participation,
            "time_alignment": round(tau[seg], 3),
            "potential_customers": float(weight.sum()),
            "walk_minutes": spec.max_walk_minutes,
            "radius_m": round(radius),
            # as the crow flies, for drawing the catchment on a map
            "straight_radius_m": round(radius / cfg.distance.detour_factor),
        }

    catchment = Catchment(**{k: np.concatenate(v) for k, v in cols.items()})
    factor, anchors = anchor_boost(sx, sy, market, profile, cfg)
    return DemandResult(catchment, float(catchment.weight.sum()), by_segment, factor, anchors)
