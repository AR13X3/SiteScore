"""Layer 7: spend. Captured customers -> visits -> revenue (and optional profit).

    visits  = sum over points of potential x fit x anchors x share x visits/month
    revenue = visits x average transaction value (adjusted for our price)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sitescore.config import SEGMENTS, BusinessProfile, Costs
from sitescore.model.demand import Catchment


@dataclass(frozen=True)
class SpendResult:
    customers: float           # captured customers per month
    visits_per_customer: float
    atv: float                 # average transaction value at our price
    visits: float              # after any capacity cap
    capacity_factor: float     # 1.0 unless the capacity cap binds
    revenue: float
    visits_by_segment: dict[str, float]           # after the cap
    uncapped_visits_by_segment: dict[str, float]  # before it (time dynamics re-apply the cap monthly)


def effective_atv(profile: BusinessProfile, price: float | None = None) -> float:
    """Basket value scales with our price relative to the reference price."""
    p = profile.pricing
    ratio = (price if price is not None else p.our_price) / p.reference_price
    return profile.spend.avg_transaction_value * ratio ** profile.spend.atv_price_elasticity


def compute_spend(catchment: Catchment, captured: np.ndarray, profile: BusinessProfile,
                  price: float | None = None) -> SpendResult:
    """captured: customers won at each catchment point (after fit, share, anchors...)."""
    visits_pts = captured * catchment.visits_per_month
    customers, visits = float(captured.sum()), float(visits_pts.sum())
    cap = profile.spend.capacity_visits_per_month
    capacity_factor = min(1.0, cap / visits) if cap and visits > 0 else 1.0
    atv = effective_atv(profile, price)
    uncapped = {s: float(visits_pts[catchment.segment == s].sum()) for s in SEGMENTS}
    return SpendResult(
        customers=customers,
        visits_per_customer=visits / customers if customers > 0 else 0.0,
        atv=atv,
        visits=visits * capacity_factor,
        capacity_factor=capacity_factor,
        revenue=visits * capacity_factor * atv,
        visits_by_segment={s: v * capacity_factor for s, v in uncapped.items()},
        uncapped_visits_by_segment=uncapped,
    )


def monthly_profit(revenue: float, costs: Costs | None) -> float | None:
    if costs is None:
        return None
    return (revenue * (1 - costs.cogs_share) - costs.rent_per_month - costs.wages_per_month
            - costs.other_fixed_per_month)
