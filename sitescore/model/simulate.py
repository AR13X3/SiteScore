"""Compare candidate sites over the horizon: evaluate, project monthly, explain.

Each site is simulated as if it were the only new store opening (the candidates
are alternatives, not a network).
"""

from __future__ import annotations

import datetime as dt

from sitescore.config import BusinessProfile, Calendar, ModelConfig, Region
from sitescore.model.dynamics import project_site
from sitescore.model.explain import explain
from sitescore.model.market import Market
from sitescore.model.site import evaluate_site
from sitescore.model.types import DataUsed, SimulationResult, Site, SiteSimulation


def default_open_date(as_of: dt.date) -> dt.date:
    """First day of the month after the as-of date."""
    return (dt.date(as_of.year, as_of.month, 1) + dt.timedelta(days=32)).replace(day=1)


def simulate(market: Market, sites: list[Site], profile: BusinessProfile, cfg: ModelConfig,
             region: Region, calendar: Calendar, open_date: dt.date | None = None
             ) -> SimulationResult:
    open_date = open_date or default_open_date(market.as_of)
    if open_date < market.as_of:
        raise ValueError("open_date must not be before the as-of date")
    sims = []
    for site in sites:
        mature = evaluate_site(market, site, profile, cfg, region)
        months, dynamics = project_site(mature, market, profile, cfg, region.metric_crs,
                                        calendar, open_date)
        profits = [m.profit for m in months]
        sims.append(SiteSimulation(
            site=site, mature=mature, months=months,
            total_revenue=sum(m.revenue for m in months),
            total_profit=None if profits[0] is None else sum(profits),
            dynamics=dynamics,
        ))
    explanations, baseline = explain(sims)
    return SimulationResult(
        business_type=profile.id,
        as_of=market.as_of,
        open_date=open_date,
        horizon_months=cfg.horizon_months,
        baseline_total_revenue=baseline,
        sites=sims,
        ranking=[e.site_id for e in explanations],
        explanations=explanations,
        data_used=[DataUsed(**a.__dict__) for a in market.data_used],
    )
