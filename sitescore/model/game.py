"""Layer 5: competitor price response (Bertrand-Nash with logit demand).

1. Before we open, assume nearby incumbents already price optimally. Their
   logit first-order condition then reveals each one's marginal cost:
       (p - c) / p = D / S,   S = sum_a w_a * e_a * P_aj * (1 - P_aj)
   (e_a = the agent's price elasticity weight).
2. Add our store. In each round every player moves part-way (damping) toward its
   best response p = c / (1 - D/S) given the others' current prices.
3. Stop when no price moves more than the tolerance. Prices stay within the
   profile's allowed range.

Demand here is the long-run (no-habit) response of the customers around our site.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sitescore.config import BusinessProfile, ModelConfig
from sitescore.model.agents import ChoiceModel


@dataclass(frozen=True)
class GameResult:
    prices_before: np.ndarray   # incumbents at reference, ours at the profile price
    prices_after: np.ndarray
    costs: np.ndarray
    players: np.ndarray         # store indices that re-optimise
    rounds: int
    converged: bool
    suggested_price: float      # our best response to competitors' final prices


def markups(model: ChoiceModel, prices: np.ndarray, ours_available: bool) -> np.ndarray:
    """(p - c)/p implied by each store's logit first-order condition."""
    probs = model.probabilities(prices, ours_available=ours_available)[:, :-1]
    w = model.agents.weight[:, None]
    demand = (w * probs).sum(axis=0)
    slope = (w * model.elasticity[:, None] * probs * (1 - probs)).sum(axis=0)
    return np.divide(demand, slope, out=np.full(len(demand), np.inf), where=slope > 0)


def solve_prices(model: ChoiceModel, profile: BusinessProfile, cfg: ModelConfig) -> GameResult:
    pricing, game = profile.pricing, cfg.game
    lo, hi = pricing.price_range
    n = len(model.stores)
    start = np.full(n, pricing.reference_price)
    start[0] = pricing.our_price

    # 1. Back out incumbents' costs from today's (pre-entry) prices. A store whose
    #    implied markup is ~100% can't be at an optimum under this demand model;
    #    it keeps today's price rather than getting an invented cost.
    m_pre = markups(model, start, ours_available=False)
    costs = pricing.reference_price * np.clip(1 - m_pre, 0.01, 1.0)
    costs[0] = pricing.unit_cost
    explainable = m_pre < 0.95

    near = model.stores.site_dist_m <= game.radius_m
    responders = np.flatnonzero(near & (explainable | (np.arange(n) == 0)))
    players = responders if game.optimise_our_price else responders[responders != 0]

    def best_response(prices: np.ndarray) -> np.ndarray:
        m = markups(model, prices, ours_available=True)
        return np.clip(np.where(m < 1, costs / np.maximum(1 - m, 1e-9), hi), lo, hi)

    if not game.enabled or len(players) == 0:
        return GameResult(start, start.copy(), costs, players, 0, True,
                          float(best_response(start)[0]))

    # 2-3. Damped simultaneous best responses until prices settle.
    prices, rounds, converged = start.copy(), game.max_rounds, False
    for r in range(1, game.max_rounds + 1):
        target = best_response(prices)
        new = prices.copy()
        new[players] += game.damping * (target[players] - prices[players])
        moved = float(np.abs(new - prices).max())
        prices = new
        if moved < game.tolerance:
            rounds, converged = r, True
            break
    return GameResult(start, prices, costs, players, rounds, converged,
                      float(best_response(prices)[0]))
