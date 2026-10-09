"""Evaluate one candidate site: run the layers and package an explainable result.

Mature monthly revenue is exactly the product of the layer factors:

    potential customers x fit x anchors x competitive share
      x ($ per captured customer) x capacity

which is what makes per-layer "why this site wins" comparisons exact.
"""

from __future__ import annotations

import math

from sitescore.config import BusinessProfile, ModelConfig, Region
from sitescore.model.demand import DemandResult, compute_demand
from sitescore.model.fit import FitResult, compute_fit
from sitescore.model.geo import project
from sitescore.model.huff import CompetitionResult, compute_competition
from sitescore.model.market import Market
from sitescore.model.spend import SpendResult, compute_spend, monthly_profit
from sitescore.model.types import DataUsed, LayerResult, Site, SiteResult

SEGMENT_LABELS = {"residents": "residents", "workers": "workers", "commuters": "commuters"}


def evaluate_site(market: Market, site: Site, profile: BusinessProfile, cfg: ModelConfig,
                  region: Region) -> SiteResult:
    xs, ys = project([site.lon], [site.lat], region.metric_crs)
    sx, sy = float(xs[0]), float(ys[0])
    demand = compute_demand(sx, sy, market, profile, cfg)
    fit = compute_fit(demand.catchment, market, profile)
    comp = compute_competition(sx, sy, demand.catchment, fit.point_multiplier, market, profile, cfg)
    spend = compute_spend(demand.catchment, fit.point_multiplier, comp.p_own,
                          demand.anchor_factor, profile)

    layers = [
        _demand_layer(demand),
        _fit_layer(fit),
        _anchor_layer(demand, profile),
        _competition_layer(comp),
        _spend_layer(spend),
    ]
    if spend.capacity_factor < 1:
        layers.append(LayerResult(
            key="capacity", label="Capacity", factor=spend.capacity_factor, unit="x",
            summary=f"Demand exceeds capacity; capped at "
                    f"{profile.spend.capacity_visits_per_month:,.0f} visits/month",
        ))
    product = math.prod(layer.factor for layer in layers)
    assert math.isclose(product, spend.revenue, rel_tol=1e-6, abs_tol=1e-6), (product, spend.revenue)

    return SiteResult(
        site=site,
        business_type=profile.id,
        as_of=market.as_of,
        monthly_visits=spend.visits,
        monthly_revenue=spend.revenue,
        monthly_profit=monthly_profit(spend.revenue, profile.costs),
        layers=layers,
        data_used=[DataUsed(**a.__dict__) for a in market.data_used],
    )


def _demand_layer(d: DemandResult) -> LayerResult:
    parts = ", ".join(f"{v['potential_customers']:,.0f} {SEGMENT_LABELS[k]}"
                      for k, v in d.by_segment.items())
    return LayerResult(
        key="demand", label="Demand", factor=d.potential_customers, unit="customers",
        summary=f"{d.potential_customers:,.0f} potential customers within walking distance "
                f"({parts}), weighted by time of day",
        details={"segments": d.by_segment},
    )


def _fit_layer(f: FitResult) -> LayerResult:
    top = f.contributions[0] if f.contributions else None
    lead = ""
    if top and abs(top["contribution"]) > 0.01:
        direction = "above" if top["catchment_z"] > 0 else "below"
        lead = (f"; biggest driver: {top['description'].lower()} is {direction} "
                f"the regional average ({top['catchment_z']:+.1f} sd)")
    return LayerResult(
        key="fit", label="Demographic fit", factor=f.factor, unit="x",
        summary=f"Local residents fit the customer profile x{f.residents_multiplier:.2f}{lead}",
        details={"index": round(f.index, 3), "residents_multiplier": round(f.residents_multiplier, 3),
                 "features": f.contributions},
    )


def _anchor_layer(d: DemandResult, profile: BusinessProfile) -> LayerResult:
    r = profile.anchors.radius_m
    if d.anchors_nearby:
        names = ", ".join(a["name"] for a in d.anchors_nearby[:3])
        more = f" +{len(d.anchors_nearby) - 3} more" if len(d.anchors_nearby) > 3 else ""
        summary = (f"Foot-traffic boost x{d.anchor_factor:.2f} from {len(d.anchors_nearby)} "
                   f"anchors within {r:.0f} m ({names}{more})")
    else:
        summary = f"No anchor tenants within {r:.0f} m"
    return LayerResult(key="anchors", label="Anchors", factor=d.anchor_factor, unit="x",
                       summary=summary, details={"anchors": d.anchors_nearby})


def _competition_layer(c: CompetitionResult) -> LayerResult:
    nearest = f", nearest {c.nearest_competitor_m:.0f} m away" if c.nearest_competitor_m else ""
    return LayerResult(
        key="competition", label="Competition", factor=c.factor, unit="share",
        summary=f"Wins {c.factor:.1%} of local demand ({c.share_if_alone:.0%} with no competitors); "
                f"{c.competitors_within_800m} competitors within 800 m{nearest}",
        details={
            "share_if_alone": round(c.share_if_alone, 4),
            "outside_share": round(c.outside_share, 4),
            "competitors_within_400m": c.competitors_within_400m,
            "competitors_within_800m": c.competitors_within_800m,
            "nearest_competitor_m": c.nearest_competitor_m,
            "top_competitors": c.top_competitors,
        },
    )


def _spend_layer(s: SpendResult) -> LayerResult:
    return LayerResult(
        key="spend", label="Spend", factor=s.visits_per_customer * s.atv, unit="$/customer",
        summary=f"{s.customers:,.0f} customers x {s.visits_per_customer:.1f} visits/month "
                f"x ${s.atv:.2f} per visit",
        details={"customers": round(s.customers, 1),
                 "visits_per_customer": round(s.visits_per_customer, 2),
                 "avg_transaction_value": round(s.atv, 2),
                 "visits_by_segment": {k: round(v) for k, v in s.visits_by_segment.items()}},
    )
