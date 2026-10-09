"""Layer 3: competition via the Huff gravity model.

A customer at point i picks store j with probability

    P_ij = A_j^alpha * d_ij^-beta / sum_k(A_k^alpha * d_ik^-beta)

summed over our store, every competitor, and an "elsewhere" option (a store
outside the modelled set, or not buying) so a lone store far from customers
doesn't win 100% by default.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sitescore.config import BusinessProfile, ModelConfig
from sitescore.model.demand import Catchment
from sitescore.model.geo import walk_distance
from sitescore.model.market import Market


def huff_probabilities(d_own: np.ndarray, d_comp: np.ndarray, a_own: float, a_comp: np.ndarray,
                       alpha: float, beta: float, outside_attr: float, outside_dist: float
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Choice probabilities. d_own: (n,), d_comp: (n, k), a_comp: (k,).

    Returns (p_own (n,), p_comp (n, k), p_outside (n,)); each row sums to 1.
    """
    u_own = a_own ** alpha * d_own ** -beta
    u_comp = (a_comp ** alpha)[None, :] * d_comp ** -beta if d_comp.size else np.zeros((len(d_own), 0))
    u_out = outside_attr ** alpha * outside_dist ** -beta
    total = u_own + u_comp.sum(axis=1) + u_out
    return u_own / total, u_comp / total[:, None], np.full(len(d_own), u_out) / total


@dataclass(frozen=True)
class CompetitionResult:
    p_own: np.ndarray          # per catchment point
    factor: float              # our share of fit-adjusted catchment demand
    share_if_alone: float      # same, with no competitors (only "elsewhere")
    outside_share: float
    competitors_within_400m: int
    competitors_within_800m: int
    nearest_competitor_m: float | None
    top_competitors: list[dict]


def compute_competition(sx: float, sy: float, catchment: Catchment, fit_mult: np.ndarray,
                        market: Market, profile: BusinessProfile, cfg: ModelConfig
                        ) -> CompetitionResult:
    h, comp = cfg.huff, market.competitors
    d_own = walk_distance(sx, sy, catchment.x, catchment.y, cfg.distance)
    d_comp = walk_distance(catchment.x[:, None], catchment.y[:, None],
                           comp.x[None, :], comp.y[None, :], cfg.distance)
    args = (profile.our_store.attractiveness, h.alpha, h.beta,
            h.outside_option.attractiveness, h.outside_option.distance_m)
    p_own, p_comp, p_out = huff_probabilities(d_own, d_comp, args[0], comp.weight, *args[1:])
    alone, _, _ = huff_probabilities(d_own, np.zeros((len(d_own), 0)), args[0],
                                     np.zeros(0), *args[1:])

    w = catchment.weight * fit_mult
    total = w.sum()

    def share(p: np.ndarray) -> float:
        return float((w * p).sum() / total) if total > 0 else 0.0

    site_to_comp = walk_distance(sx, sy, comp.x, comp.y, cfg.distance, floor=False)
    taken = (w[:, None] * p_comp).sum(axis=0) / total if total > 0 else np.zeros(len(comp))
    top = np.argsort(-taken)[:5]
    return CompetitionResult(
        p_own=p_own,
        factor=share(p_own),
        share_if_alone=share(alone),
        outside_share=share(p_out),
        competitors_within_400m=int((site_to_comp <= 400).sum()),
        competitors_within_800m=int((site_to_comp <= 800).sum()),
        nearest_competitor_m=round(float(site_to_comp.min())) if len(comp) else None,
        top_competitors=[
            {"name": str(comp.names[i]) or "unnamed", "osm_id": str(comp.ids[i]),
             "lat": float(comp.lat[i]), "lon": float(comp.lon[i]),
             "distance_m": round(float(site_to_comp[i])),
             "share_of_local_demand": round(float(taken[i]), 4)}
            for i in top if taken[i] > 0
        ],
    )
