"""Evaluate one candidate site: run the layers and package an explainable result.

Mature monthly revenue is exactly the product of the layer factors:

    potential customers x fit x anchors x gravity share
      x customer behaviour (agents) x price response (game)
      x ($ per captured customer) x capacity

which is what makes per-layer "why this site wins" comparisons exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from sitescore.config import BusinessProfile, ModelConfig, Region
from sitescore.model.abm import AbmResult, simulate
from sitescore.model.agents import ChoiceModel, StoreSet, build_agents, build_stores
from sitescore.model.demand import DemandResult, compute_demand
from sitescore.model.dynamics import ramp_curve
from sitescore.model.fit import FitResult, compute_fit
from sitescore.model.game import GameResult, solve_prices
from sitescore.model.geo import project
from sitescore.model.huff import CompetitionResult, compute_competition
from sitescore.model.market import Market
from sitescore.model.spend import SpendResult, compute_spend, monthly_profit
from sitescore.model.types import DataUsed, LayerResult, Site, SiteResult

SEGMENT_LABELS = {"residents": "residents", "workers": "workers", "commuters": "commuters"}


@dataclass(frozen=True)
class AgentOutcome:
    behaviour_factor: float   # agents at today's prices vs plain Huff on the same agents
    price_factor: float       # after competitors (and we) re-price vs before
    captured: np.ndarray      # captured customers per catchment point (incl. anchors)
    our_price: float
    ramp: np.ndarray          # our customers each month / steady state
    sim: AbmResult
    game: GameResult
    stores: StoreSet
    n_agents: int


def run_agents(sx: float, sy: float, demand: DemandResult, fit: FitResult,
               huff_customers: float, market: Market, profile: BusinessProfile,
               cfg: ModelConfig) -> AgentOutcome:
    """Layers 4 and 5: price game, then month-by-month agent simulation."""
    agents = build_agents(demand.catchment, fit.point_multiplier, cfg)
    stores = build_stores(sx, sy, demand.catchment, market, profile, cfg)
    model = ChoiceModel(agents, stores, profile, cfg)
    huff_on_agents = model.customers(model.huff_probabilities())[0]

    game = solve_prices(model, profile, cfg)
    before = model.customers(model.probabilities(game.prices_before))[0]
    sim = simulate(model, game.prices_after, ramp_curve(cfg.horizon_months, profile.dynamics), cfg)

    # Agents use nearby competitors only; rescale so "plain Huff" matches the full
    # competition layer, then everything agents add is a clean ratio on top.
    scale = huff_customers / huff_on_agents * demand.anchor_factor
    captured = np.bincount(agents.point, weights=agents.weight * sim.steady_probs[:, 0],
                           minlength=len(demand.catchment.weight)) * scale
    steady = sim.steady_customers
    return AgentOutcome(
        behaviour_factor=before / huff_on_agents,
        price_factor=steady / before if before > 0 else 1.0,
        captured=captured,
        our_price=float(game.prices_after[0]),
        ramp=sim.monthly_customers / steady if steady > 0 else np.ones(cfg.horizon_months),
        sim=sim, game=game, stores=stores, n_agents=len(agents),
    )


def evaluate_site(market: Market, site: Site, profile: BusinessProfile, cfg: ModelConfig,
                  region: Region) -> SiteResult:
    xs, ys = project([site.lon], [site.lat], region.metric_crs)
    sx, sy = float(xs[0]), float(ys[0])
    demand = compute_demand(sx, sy, market, profile, cfg)
    fit = compute_fit(demand.catchment, market, profile)
    comp = compute_competition(sx, sy, demand.catchment, fit.point_multiplier, market, profile, cfg)
    captured = demand.catchment.weight * fit.point_multiplier * comp.p_own * demand.anchor_factor

    agent = None
    if cfg.abm.enabled and captured.sum() > 0:
        agent = run_agents(sx, sy, demand, fit, float(captured.sum() / demand.anchor_factor),
                           market, profile, cfg)
        captured = agent.captured
    spend = compute_spend(demand.catchment, captured, profile,
                          price=agent.our_price if agent else None)

    layers = [
        _demand_layer(demand),
        _fit_layer(fit),
        _anchor_layer(demand, profile),
        _competition_layer(comp),
    ]
    if agent:
        layers += [_behaviour_layer(agent), _price_layer(agent, profile, cfg)]
    layers.append(_spend_layer(spend))
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
        avg_transaction_value=spend.atv,
        segment_visits=spend.uncapped_visits_by_segment,
        ramp=[float(r) for r in agent.ramp] if agent else None,
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


def _behaviour_layer(a: AgentOutcome) -> LayerResult:
    m90 = a.sim.months_to_90pct
    ramp = f"; with habits, trade reaches 90% of the long run in month {m90}" if m90 else ""
    effect = "more" if a.behaviour_factor >= 1 else "less"
    return LayerResult(
        key="behaviour", label="Customer behaviour", factor=a.behaviour_factor, unit="x",
        summary=f"{a.n_agents:,} simulated customers with varied tastes choose us {effect} often "
                f"than the plain gravity model predicts (x{a.behaviour_factor:.2f}), incl. our "
                f"quality edge{ramp}",
        details={"agents": a.n_agents, "stores_considered": len(a.stores) - 1,
                 "months_to_90pct": m90, "ramp": [round(float(r), 3) for r in a.ramp[:12]]},
    )


def _price_layer(a: AgentOutcome, profile: BusinessProfile, cfg: ModelConfig) -> LayerResult:
    g, s = a.game, a.stores
    rivals = [i for i in g.players if i != 0]
    if rivals:
        before, after = g.prices_before[rivals].mean(), g.prices_after[rivals].mean()
        lead = (f"{len(rivals)} competitors within {cfg.game.radius_m:.0f} m respond: average "
                f"price ${before:.2f} -> ${after:.2f}")
    else:
        lead = f"No competitors within {cfg.game.radius_m:.0f} m to respond"
    lo, hi = profile.pricing.price_range
    if cfg.game.optimise_our_price:
        ours = f"; our price set by the model: ${a.our_price:.2f}"
    elif lo < g.suggested_price < hi and abs(g.suggested_price - a.our_price) >= 0.05:
        ours = (f"; we charge ${a.our_price:.2f} (margin-maximising price here: "
                f"${g.suggested_price:.2f})")
    else:
        ours = f"; we charge ${a.our_price:.2f}"
    return LayerResult(
        key="price", label="Price response", factor=a.price_factor, unit="x",
        summary=f"{lead}{ours}; our share x{a.price_factor:.2f}",
        details={
            "our_price_before": round(float(g.prices_before[0]), 2),
            "our_price_after": round(a.our_price, 2),
            "suggested_price": round(g.suggested_price, 2),
            "reference_price": profile.pricing.reference_price,
            "rounds": g.rounds, "converged": g.converged,
            "competitors": sorted(
                ({"name": str(s.names[i]) or "unnamed", "distance_m": round(float(s.site_dist_m[i])),
                  "price_before": round(float(g.prices_before[i]), 2),
                  "price_after": round(float(g.prices_after[i]), 2),
                  "implied_cost": round(float(g.costs[i]), 2)} for i in rivals),
                key=lambda c: c["distance_m"]),
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
