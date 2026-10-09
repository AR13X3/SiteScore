"""Layer 4: agent-based simulation of customers choosing stores month by month.

Before we open, every agent splits its visits across incumbents and "elsewhere"
by its own logit probabilities (agents.py). From opening:

- awareness: in month t only a(t) of agents know we exist (the profile's ramp
  curve); unaware agents choose as if we weren't there;
- habit: each month only a share r of customers reconsider; the rest repeat
  last month's pattern:  P_t = r * P*_t + (1 - r) * P_{t-1}.

The long-run state (everyone aware, habits caught up) is the plain choice
model, so habits shape the ramp-up but not who wins in the long run. Expected
choices are tracked rather than sampled, so results are smooth and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sitescore.config import ModelConfig
from sitescore.model.agents import ChoiceModel


@dataclass(frozen=True)
class AbmResult:
    monthly_customers: np.ndarray   # our expected customers in each month since opening
    steady_customers: float         # long run: everyone aware, habits caught up
    steady_probs: np.ndarray        # (n_agents, n_stores + 1) long-run choice probabilities
    months_to_90pct: int | None     # first month our customers reach 90% of the long run


def simulate(model: ChoiceModel, prices: np.ndarray, awareness: np.ndarray,
             cfg: ModelConfig) -> AbmResult:
    r = cfg.abm.monthly_reconsider_share
    aware = model.probabilities(prices, ours_available=True)
    unaware = model.probabilities(prices, ours_available=False)

    probs = unaware  # the market before we open
    monthly = np.empty(len(awareness))
    for t, a in enumerate(awareness):
        probs = r * (a * aware + (1 - a) * unaware) + (1 - r) * probs
        monthly[t] = model.customers(probs)[0]

    steady = float(model.customers(aware)[0])
    reached = np.flatnonzero(monthly >= 0.9 * steady) if steady > 0 else np.array([])
    return AbmResult(monthly, steady, aware, int(reached[0]) + 1 if len(reached) else None)
