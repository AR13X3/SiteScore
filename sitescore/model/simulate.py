"""Compare candidate sites over the horizon: evaluate, project monthly, explain, add bands.

Each site is simulated as if it were the only new store opening (the candidates
are alternatives, not a network). The base case (every assumption at its central
value) drives the ranking and the "why"; Monte Carlo adds P10/P50/P90 bands and
each site's chance of being the best.
"""

from __future__ import annotations

import datetime as dt

from sitescore.config import BusinessProfile, Calendar, ModelConfig, Region
from sitescore.model.dynamics import monthly_components, project_site
from sitescore.model.explain import explain
from sitescore.model.market import Market
from sitescore.model.montecarlo import run_uncertainty
from sitescore.model.site import analyse_site
from sitescore.model.types import DataUsed, SimulationResult, Site, SiteSimulation


def default_open_date(as_of: dt.date) -> dt.date:
    """First day of the month after the as-of date."""
    return (dt.date(as_of.year, as_of.month, 1) + dt.timedelta(days=32)).replace(day=1)


def simulate(market: Market, sites: list[Site], profile: BusinessProfile, cfg: ModelConfig,
             region: Region, calendar: Calendar, open_date: dt.date | None = None,
             uncertainty: bool = False, n_runs: int | None = None,
             uncertainty_top: int | None = None,
             uncertainty_by: str = "revenue") -> SimulationResult:
    """uncertainty_top: Monte Carlo bands only for the n best sites by total revenue
    (or profit, with uncertainty_by="profit"): the spot finder ranks many sites but
    only needs ranges for the winners."""
    open_date = open_date or default_open_date(market.as_of)
    if open_date < market.as_of:
        raise ValueError("open_date must not be before the as-of date")
    sims, analyses, components = [], [], []
    for site in sites:
        analysis = analyse_site(market, site, profile, cfg, region)
        months, dynamics = project_site(analysis.result, market, profile, cfg, region.metric_crs,
                                        calendar, open_date)
        profits = [m.profit for m in months]
        sims.append(SiteSimulation(
            site=site, mature=analysis.result, months=months,
            total_revenue=sum(m.revenue for m in months),
            total_profit=None if profits[0] is None else sum(profits),
            dynamics=dynamics,
        ))
        analyses.append(analysis)
    banded = list(range(len(sims)))
    if uncertainty and uncertainty_top:
        def value(i: int) -> float:
            p = sims[i].total_profit
            return p if uncertainty_by == "profit" and p is not None else sims[i].total_revenue
        banded = sorted(banded, key=value, reverse=True)[:uncertainty_top]
    if uncertainty:
        components = [monthly_components(analyses[i].result, market, profile, cfg,
                                         region.metric_crs, calendar, open_date) for i in banded]
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
        uncertainty=run_uncertainty([analyses[i] for i in banded], components, market, profile,
                                    cfg, region, calendar, open_date, n_runs)
        if uncertainty else None,
    )
