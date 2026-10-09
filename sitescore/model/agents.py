"""Virtual customers and the logit choice model shared by the agent (4) and game (5) layers.

An agent is a (demand point, customer type) pair: every point in the catchment
gets the same K customer types, so heterogeneity is identical everywhere and the
results don't jitter with random sampling. Each agent represents weight/K of the
point's fit-adjusted potential customers.

Utility of agent a for store j:

    alpha*log(A_j) - beta*m_dist_a*log(d_aj)                 <- the Huff model
    - elasticity*m_price_a*log(p_j / p_ref)                  <- price
    + quality_w*m_quality_a*q_j                              <- quality

and "elsewhere" has alpha*log(A_0) - beta*m_dist_a*log(d_0). With m = 1,
prices at reference and no quality gap, the choice probabilities equal Huff
exactly. Habits act over time (abm.py), not in the utility.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sitescore.config import BusinessProfile, ModelConfig
from sitescore.model.demand import Catchment
from sitescore.model.geo import walk_distance
from sitescore.model.market import Market


@dataclass(frozen=True)
class Agents:
    point: np.ndarray      # catchment point each agent lives/works at
    segment: np.ndarray
    weight: np.ndarray     # potential customers this agent represents
    visits: np.ndarray     # visits per month when it chooses a store
    m_dist: np.ndarray     # preference multipliers, mean 1
    m_price: np.ndarray
    m_quality: np.ndarray

    def __len__(self) -> int:
        return len(self.weight)


@dataclass(frozen=True)
class StoreSet:
    """Stores agents choose between. Index 0 is always our store."""

    ids: np.ndarray
    names: np.ndarray
    log_attract: np.ndarray    # alpha * log(attractiveness), per store
    log_dist: np.ndarray       # (n_points, n_stores) log walking distance from each point
    quality: np.ndarray        # quality z-score; competitors 0 (unknown)
    site_dist_m: np.ndarray    # distance from our site to each store
    out_log_attract: float
    out_log_dist: float

    def __len__(self) -> int:
        return len(self.ids)


def build_agents(catchment: Catchment, fit_mult: np.ndarray, cfg: ModelConfig) -> Agents:
    n_points = len(catchment.weight)
    k = int(np.clip(round(cfg.abm.n_agents / max(n_points, 1)), 4, 64))
    rng = np.random.default_rng(cfg.abm.seed)
    sigma = cfg.abm.heterogeneity_sigma
    # Lognormal multipliers with mean 1; K types shared by every point.
    types = np.exp(rng.normal(-sigma ** 2 / 2, sigma, size=(3, k))) if sigma > 0 else np.ones((3, k))
    point = np.repeat(np.arange(n_points), k)
    return Agents(
        point=point,
        segment=catchment.segment[point],
        weight=(catchment.weight * fit_mult)[point] / k,
        visits=catchment.visits_per_month[point],
        m_dist=np.tile(types[0], n_points),
        m_price=np.tile(types[1], n_points),
        m_quality=np.tile(types[2], n_points),
    )


def build_stores(sx: float, sy: float, catchment: Catchment, market: Market,
                 profile: BusinessProfile, cfg: ModelConfig) -> StoreSet:
    comp = market.competitors
    site_to_comp = walk_distance(sx, sy, comp.x, comp.y, cfg.distance, floor=False)
    keep = np.flatnonzero(site_to_comp <= cfg.abm.competitor_radius_m)
    xs = np.concatenate([[sx], comp.x[keep]])
    ys = np.concatenate([[sy], comp.y[keep]])
    attract = np.concatenate([[profile.our_store.attractiveness], comp.weight[keep]])
    d = walk_distance(catchment.x[:, None], catchment.y[:, None], xs[None, :], ys[None, :],
                      cfg.distance)
    h = cfg.huff
    return StoreSet(
        ids=np.concatenate([["our-store"], comp.ids[keep]]),
        names=np.concatenate([["Our store"], comp.names[keep]]),
        log_attract=h.alpha * np.log(attract),
        log_dist=np.log(d),
        quality=np.concatenate([[profile.our_store.quality], np.zeros(len(keep))]),
        site_dist_m=np.concatenate([[0.0], site_to_comp[keep]]),
        out_log_attract=h.alpha * np.log(h.outside_option.attractiveness),
        out_log_dist=float(np.log(h.outside_option.distance_m)),
    )


class ChoiceModel:
    """Logit choice probabilities for every agent over (stores..., elsewhere)."""

    def __init__(self, agents: Agents, stores: StoreSet, profile: BusinessProfile,
                 cfg: ModelConfig):
        beta = cfg.huff.beta
        self.agents, self.stores = agents, stores
        self.ref_price = profile.pricing.reference_price
        self.elasticity = profile.pricing.price_elasticity * agents.m_price  # (n,)
        log_d = stores.log_dist[agents.point]                                # (n, k)
        self._static = (stores.log_attract[None, :] - beta * agents.m_dist[:, None] * log_d
                        + cfg.abm.utility.quality * agents.m_quality[:, None] * stores.quality[None, :])
        self._static_out = stores.out_log_attract - beta * agents.m_dist * stores.out_log_dist
        # Plain Huff (homogeneous, no price/quality/habit) on the same store set.
        self._huff = stores.log_attract[None, :] - beta * log_d
        self._huff_out = np.full(len(agents), stores.out_log_attract - beta * stores.out_log_dist)

    def probabilities(self, prices: np.ndarray, ours_available: bool = True) -> np.ndarray:
        """(n_agents, n_stores + 1) choice probabilities; the last column is 'elsewhere'."""
        v = self._static - self.elasticity[:, None] * np.log(prices / self.ref_price)[None, :]
        if not ours_available:
            v[:, 0] = -np.inf
        return _softmax(np.column_stack([v, self._static_out]))

    def huff_probabilities(self) -> np.ndarray:
        return _softmax(np.column_stack([self._huff, self._huff_out]))

    def customers(self, probs: np.ndarray) -> np.ndarray:
        """Expected customers per option (weighted by what each agent represents)."""
        return self.agents.weight @ probs


def _softmax(v: np.ndarray) -> np.ndarray:
    e = np.exp(v - v.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)
