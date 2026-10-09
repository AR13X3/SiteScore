"""Site-specific rent: what a shopfront here probably costs.

There's no open data on commercial asking rents, so rent is an index on the
business profile's rent for a TYPICAL site:

    rent = rent_per_month x (foot traffic / typical) ^ footfall_elasticity
                          x (local residential rent / regional) ^ area_rent_elasticity

- Foot traffic: people within walking reach of the site, weighted by how much
  they're around when this business trades, times the anchor boost. Participation
  isn't included, so rent doesn't move with assumptions about who buys coffee.
- Typical: the median foot traffic at the locations where this kind of business
  already trades (in the market as of the run date).
- Local rents: the population-weighted median weekly rent (Census) within
  area_radius_m, against the same median across the whole market.

Landlords price shopfronts by passing trade, and local rents stand in for land
values. The elasticities are assumptions (config/model.yaml) until real asking
rents or Valuer General land values can calibrate them.
"""

from __future__ import annotations

import numpy as np

from sitescore.config import BusinessProfile, ModelConfig
from sitescore.model.demand import DemandResult, compute_demand
from sitescore.model.market import Market
from sitescore.model.types import RentEstimate


def foot_traffic(demand: DemandResult) -> float:
    """People in walking reach, weighted by time alignment, times the anchor boost."""
    people = sum(seg["people_in_reach"] * seg["time_alignment"] for seg in demand.by_segment.values())
    return float(people * demand.anchor_factor)


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    ok = ~np.isnan(values) & (weights > 0)
    if not ok.any():
        return None
    v, w = values[ok], weights[ok]
    order = np.argsort(v)
    cum = np.cumsum(w[order])
    return float(v[order][np.searchsorted(cum, cum[-1] / 2)])


def typical(market: Market, profile: BusinessProfile, cfg: ModelConfig) -> tuple[float, float | None]:
    """(median foot traffic at existing sites of this type, regional median rent), memoised."""
    key = ("rent_typical", profile.id, cfg.rent.model_dump_json(), cfg.distance.model_dump_json())
    if key not in market.memo:
        comp = market.competitors
        primary = comp.primary if comp.primary is not None else np.ones(len(comp), bool)
        idx = np.flatnonzero(primary) if primary.any() else np.arange(len(comp))
        traffic = [foot_traffic(compute_demand(float(comp.x[i]), float(comp.y[i]), market, profile, cfg))
                   for i in idx]
        rents = market.resident_features["median_rent_weekly"].to_numpy(float)
        market.memo[key] = (float(np.median(traffic)) if traffic else 0.0,
                            weighted_median(rents, market.residents.people))
    return market.memo[key]


def estimate_rent(sx: float, sy: float, demand: DemandResult, market: Market,
                  profile: BusinessProfile, cfg: ModelConfig) -> RentEstimate | None:
    if profile.costs is None or not cfg.rent.enabled:
        return None
    r, base = cfg.rent, profile.costs.rent_per_month
    typical_traffic, regional_rent = typical(market, profile, cfg)
    traffic = foot_traffic(demand)
    footfall_index = traffic / typical_traffic if typical_traffic > 0 else 1.0

    res = market.residents
    near = np.hypot(res.x - sx, res.y - sy) <= r.area_radius_m
    rents = market.resident_features["median_rent_weekly"].to_numpy(float)
    local = weighted_median(rents[near], res.people[near]) if near.any() else None
    area_index = local / regional_rent if local and regional_rent else 1.0

    lo, hi = r.index_range
    raw = max(footfall_index, 1e-6) ** r.footfall_elasticity * area_index ** r.area_rent_elasticity
    index = float(np.clip(raw, lo, hi))
    parts = [f"foot traffic x{footfall_index:.2f} of a typical site"]
    if local:
        parts.append(f"local rents ${local:,.0f}/week vs ${regional_rent:,.0f} regional")
    capped = " (capped)" if raw != index else ""
    return RentEstimate(
        monthly=base * index, base=base, index=index, footfall_index=footfall_index,
        area_index=area_index,
        summary=(f"Estimated rent ${base * index:,.0f}/month, x{index:.2f} the typical "
                 f"${base:,.0f}{capped}: " + "; ".join(parts)),
    )
