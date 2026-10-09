"""Layer 8: Monte Carlo uncertainty. P10/P50/P90 revenue bands and win chances.

Every run draws the uncertain assumptions listed in model.yaml (montecarlo.
parameters). All sites share the same draws (common random numbers), so the
"chance each site is best" compares like with like.

Fast mode (default) uses the exact factor structure of the model instead of
re-running it per draw. For each site:

- participation, visits/month, average spend: exact rescaling per segment;
- Huff distance decay (beta) and the "elsewhere" distance: Huff shares are
  recomputed for all draws at once on the site's own demand points;
- price elasticity: the price game and agent shares are re-solved on a small
  grid of elasticities around the base and interpolated;
- awareness ramp and habit: the agent ramp has a closed form,
  x_t = r * a_t + (1 - r) * x_{t-1}, so it is recomputed exactly.

At the central values every ratio is 1, so fast mode reproduces the base run
exactly. Full mode re-runs the whole model per draw (for validation).
"""

from __future__ import annotations

import datetime as dt
import fnmatch
from dataclasses import dataclass, replace

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from sitescore.config import (
    SEGMENTS,
    BusinessProfile,
    Calendar,
    Distribution,
    ModelConfig,
    NormalRel,
    Region,
    Triangular,
    expand_path,
    get_path,
    set_path,
)
from sitescore.model.agents import ChoiceModel
from sitescore.model.dynamics import (
    MonthlyComponents,
    assemble,
    project_site,
    ramp_curve,
)
from sitescore.model.game import solve_prices
from sitescore.model.huff import compute_competition
from sitescore.model.market import Market
from sitescore.model.site import SiteAnalysis, analyse_site
from sitescore.model.spend import site_costs
from sitescore.model.types import (
    Band,
    ParameterRange,
    RentEstimate,
    Site,
    SiteUncertainty,
    Uncertainty,
)

# Parameters fast mode knows how to re-apply. Anything else needs mode: full.
FAST_PARAMETERS = (
    "profile.spend.avg_transaction_value",
    "profile.segments.*.participation",
    "profile.segments.*.visits_per_month",
    "profile.dynamics.ramp_months_to_90pct",
    "profile.dynamics.ramp_start_share",
    "profile.pricing.price_elasticity",
    "model.huff.beta",
    "model.huff.outside_option.distance_m",
    "model.abm.monthly_reconsider_share",
)
ELASTICITY_GRID = (0.6, 0.8, 1.0, 1.2, 1.4)  # x base elasticity; covers +-2.7 sd at sd 15%


# --- Sampling --------------------------------------------------------------------------


def check_fast_supported(cfg: ModelConfig) -> None:
    bad = [p for p in cfg.montecarlo.parameters
           if not any(fnmatch.fnmatch(p, f) for f in FAST_PARAMETERS)]
    if bad:
        raise ValueError(f"montecarlo mode 'fast' can't vary {bad}; use mode: full "
                         f"or one of {list(FAST_PARAMETERS)}")


def _draw(dist: Distribution, base: float, rng: np.random.Generator, n: int) -> np.ndarray:
    if isinstance(dist, NormalRel):
        return base * (1 + dist.sd * rng.standard_normal(n))
    if isinstance(dist, Triangular):
        return rng.triangular(dist.low, dist.mode, dist.high, n)
    return rng.uniform(dist.low, dist.high, n)


def _clip(path: str, values: np.ndarray) -> np.ndarray:
    if path.endswith("participation"):
        return np.clip(values, 0.0, 1.0)
    if path.endswith("ramp_start_share"):
        return np.clip(values, 0.01, 0.99)
    if path.endswith("monthly_reconsider_share"):
        return np.clip(values, 0.01, 1.0)
    return np.maximum(values, 1e-6)


def sample_parameters(cfg: ModelConfig, profile: BusinessProfile, n: int, seed: int
                      ) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    """Draws per concrete parameter path, and each path's base value."""
    rng = np.random.default_rng(seed)
    data = {"profile": profile.model_dump(), "model": cfg.model_dump()}
    draws, base = {}, {}
    for pattern, dist in cfg.montecarlo.parameters.items():
        scope, rest = pattern.split(".", 1)
        for path in expand_path(data[scope], rest):
            key = f"{scope}.{path}"
            base[key] = float(get_path(data[scope], path))
            draws[key] = _clip(key, _draw(dist, base[key], rng, n))
    return draws, base


def _value(draws: dict, base: dict, key: str, fallback: float, n: int) -> np.ndarray:
    return draws[key] if key in draws else np.full(n, base.get(key, fallback))


# --- Fast mode ----------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteDraws:
    revenue: np.ndarray          # (n_runs, months)
    profit: np.ndarray | None    # (n_runs, months)


CHOICE_GRID_POINTS = (5, 4)  # grid size over (Huff beta, "elsewhere" distance)


@dataclass(frozen=True)
class ChoiceSurface:
    """Per-segment choice quantities on a (beta, d0) grid, per unit of participation.

    huff_full:   our Huff customers against every competitor (the competition layer)
    huff_agents: the same on the agents' nearby store set (the behaviour baseline)
    agents_ref:  agents' customers at today's prices
    In the full model a segment's visits are proportional to
        [sum_s part_s * huff_full_s / sum_s part_s * huff_agents_s] * part_s * agents_ref_s
    (times the price-game effect and visits/month), so evaluating these on a grid
    and interpolating reproduces it for any draw.
    """

    betas: np.ndarray
    d0s: np.ndarray
    huff_full: dict[str, np.ndarray]    # each (len(betas), len(d0s))
    huff_agents: dict[str, np.ndarray]
    agents_ref: dict[str, np.ndarray]

    def at(self, beta: np.ndarray, d0: np.ndarray) -> tuple[dict, dict, dict]:
        points = np.column_stack([beta, d0])

        def interp(table: np.ndarray) -> np.ndarray:
            return RegularGridInterpolator((self.betas, self.d0s), table)(points)

        return tuple({s: interp(t[s]) for s in SEGMENTS}
                     for t in (self.huff_full, self.huff_agents, self.agents_ref))


def _grid(values: np.ndarray, base: float, k: int) -> np.ndarray:
    """k points spanning the draws, always including the base value exactly."""
    lo, hi = float(min(values.min(), base)), float(max(values.max(), base))
    if hi - lo < 1e-9:
        return np.array([base - 1e-6, base, base + 1e-6])
    return np.unique(np.append(np.linspace(lo, hi, k), base))


def _per_segment(values: np.ndarray, segment: np.ndarray, profile: BusinessProfile) -> dict:
    """Sum per segment, divided by that segment's participation (0 if unused)."""
    out = {}
    for seg in SEGMENTS:
        part = profile.segments[seg].participation
        out[seg] = float(values[segment == seg].sum()) / part if part > 0 else 0.0
    return out


def choice_surface(a: SiteAnalysis, market: Market, profile: BusinessProfile, cfg: ModelConfig,
                   beta: np.ndarray, d0: np.ndarray) -> ChoiceSurface:
    c, h = a.demand.catchment, cfg.huff
    betas = _grid(beta, h.beta, CHOICE_GRID_POINTS[0])
    d0s = _grid(d0, h.outside_option.distance_m, CHOICE_GRID_POINTS[1])
    shape = (len(betas), len(d0s))
    tables = {name: {s: np.zeros(shape) for s in SEGMENTS}
              for name in ("huff_full", "huff_agents", "agents_ref")}
    w = c.weight * a.fit.point_multiplier
    for i, b in enumerate(betas):
        for j, d in enumerate(d0s):
            cfg_ij = cfg.model_copy(update={"huff": h.model_copy(update={
                "beta": float(b), "outside_option": h.outside_option.model_copy(
                    update={"distance_m": float(d)})})})
            comp = compute_competition(a.sx, a.sy, c, a.fit.point_multiplier, market, profile,
                                       cfg_ij)
            full = _per_segment(w * comp.p_own, c.segment, profile)
            if a.agent is None:
                agents_huff = agents_ref = full
            else:
                stores = replace(a.agent.stores, out_log_dist=float(np.log(d)))
                model = ChoiceModel(a.agent.model.agents, stores, profile, cfg_ij)
                ag = model.agents
                agents_huff = _per_segment(ag.weight * model.huff_probabilities()[:, 0],
                                           ag.segment, profile)
                agents_ref = _per_segment(
                    ag.weight * model.probabilities(a.agent.game.prices_before)[:, 0],
                    ag.segment, profile)
            for s in SEGMENTS:
                tables["huff_full"][s][i, j] = full[s]
                tables["huff_agents"][s][i, j] = agents_huff[s]
                tables["agents_ref"][s][i, j] = agents_ref[s]
    return ChoiceSurface(betas, d0s, **tables)


def price_effect(a: SiteAnalysis, profile: BusinessProfile, cfg: ModelConfig,
                 elasticity: np.ndarray) -> dict[str, np.ndarray]:
    """Per segment: agents' customers at the price game's outcome / at today's prices."""
    if a.agent is None:
        return {s: np.ones(len(elasticity)) for s in SEGMENTS}
    agents, base_e = a.agent.model.agents, profile.pricing.price_elasticity
    grid, rows = [], []
    for mult in ELASTICITY_GRID:
        p = profile.model_copy(update={"pricing": profile.pricing.model_copy(
            update={"price_elasticity": base_e * mult})})
        model = ChoiceModel(agents, a.agent.stores, p, cfg)
        game = solve_prices(model, p, cfg)
        after = _per_segment(agents.weight * model.probabilities(game.prices_after)[:, 0],
                             agents.segment, profile)
        before = _per_segment(agents.weight * model.probabilities(game.prices_before)[:, 0],
                              agents.segment, profile)
        grid.append(base_e * mult)
        rows.append({s: after[s] / before[s] if before[s] > 0 else 1.0 for s in SEGMENTS})
    return {s: np.interp(elasticity, grid, [r[s] for r in rows]) for s in SEGMENTS}


def _ramps(profile: BusinessProfile, cfg: ModelConfig, start: np.ndarray, months90: np.ndarray,
           reconsider: np.ndarray, n_months: int) -> np.ndarray:
    """(n_runs, months) ramp: awareness curve, then habit lag if agents are on."""
    out = np.empty((len(start), n_months))
    for i in range(len(start)):
        dyn = profile.dynamics.model_copy(update={"ramp_start_share": float(start[i]),
                                                  "ramp_months_to_90pct": float(months90[i])})
        out[i] = ramp_curve(n_months, dyn)
    if not cfg.abm.enabled:
        return out
    x = np.zeros(len(start))
    for t in range(n_months):  # same recursion as abm.simulate, relative to the long run
        x = reconsider * out[:, t] + (1 - reconsider) * x
        out[:, t] = x
    return out


def _segment_visits(part: dict, visits: dict, surface: tuple, price: dict
                    ) -> dict[str, np.ndarray]:
    """Visits per segment up to a constant, following the full model's chain."""
    huff_full, huff_agents, agents_ref = surface
    num = sum(part[s] * huff_full[s] for s in SEGMENTS)
    den = sum(part[s] * huff_agents[s] for s in SEGMENTS)
    scale = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
    return {s: scale * part[s] * agents_ref[s] * price[s] * visits[s] for s in SEGMENTS}


def fast_site_draws(a: SiteAnalysis, comp: MonthlyComponents, market: Market,
                    profile: BusinessProfile, cfg: ModelConfig, draws: dict[str, np.ndarray],
                    base: dict[str, float], n: int) -> SiteDraws:
    months = len(comp.months)
    if a.result.monthly_revenue <= 0 and not comp.development.any():
        zeros = np.zeros((n, months))
        return SiteDraws(zeros, _profit(zeros, profile, a.result.rent))

    def pv(key: str, fallback: float) -> np.ndarray:
        return _value(draws, base, key, fallback, n)

    h, seg = cfg.huff, profile.segments
    beta = pv("model.huff.beta", h.beta)
    d0 = pv("model.huff.outside_option.distance_m", h.outside_option.distance_m)
    elasticity = pv("profile.pricing.price_elasticity", profile.pricing.price_elasticity)
    surface = choice_surface(a, market, profile, cfg, beta, d0)
    price = price_effect(a, profile, cfg, np.append(elasticity, profile.pricing.price_elasticity))

    part = {s: pv(f"profile.segments.{s}.participation", seg[s].participation) for s in SEGMENTS}
    visits = {s: pv(f"profile.segments.{s}.visits_per_month", seg[s].visits_per_month)
              for s in SEGMENTS}
    drawn = _segment_visits(part, visits, surface.at(beta, d0),
                            {s: v[:-1] for s, v in price.items()})
    central = _segment_visits(
        {s: np.array([seg[s].participation]) for s in SEGMENTS},
        {s: np.array([seg[s].visits_per_month]) for s in SEGMENTS},
        surface.at(np.array([h.beta]), np.array([h.outside_option.distance_m])),
        {s: v[-1:] for s, v in price.items()})
    ratio = {s: np.divide(drawn[s], central[s][0], out=np.ones(n), where=central[s][0] > 0)
             for s in SEGMENTS}

    base_visits = sum(comp.base_by_segment[s][None, :] * ratio[s][:, None] for s in SEGMENTS)
    development = comp.development[None, :] * ratio["residents"][:, None]
    ramp = _ramps(profile, cfg,
                  pv("profile.dynamics.ramp_start_share", profile.dynamics.ramp_start_share),
                  pv("profile.dynamics.ramp_months_to_90pct",
                     profile.dynamics.ramp_months_to_90pct),
                  pv("model.abm.monthly_reconsider_share", cfg.abm.monthly_reconsider_share),
                  months)
    atv_draw = pv("profile.spend.avg_transaction_value", profile.spend.avg_transaction_value)
    atv = comp.atv * atv_draw / profile.spend.avg_transaction_value
    _, revenue, _ = assemble(base_visits, development, ramp, atv, comp.capacity)
    return SiteDraws(revenue, _profit(revenue, profile, a.result.rent))


def _relative(values: np.ndarray, base: float) -> np.ndarray:
    """values / base; a parameter that is 0 at base (segment unused) stays unused."""
    return values / base if base > 0 else np.ones_like(values)


def _profit(revenue: np.ndarray, profile: BusinessProfile, rent: RentEstimate | None
            ) -> np.ndarray | None:
    """Monthly profit draws with this site's rent (rent itself isn't drawn)."""
    c = site_costs(profile.costs, rent)
    if c is None:
        return None
    return revenue * (1 - c.cogs_share) - (c.rent_per_month + c.wages_per_month
                                           + c.other_fixed_per_month)


# --- Full mode -----------------------------------------------------------------------------


def full_site_draws(market: Market, site: Site, profile: BusinessProfile, cfg: ModelConfig,
                    region: Region, calendar: Calendar, open_date: dt.date,
                    draws: dict[str, np.ndarray], n: int) -> SiteDraws:
    revenue = np.empty((n, cfg.horizon_months))
    rent = None
    for i in range(n):
        p_data, m_data = profile.model_dump(), cfg.model_dump()
        for key, values in draws.items():
            scope, path = key.split(".", 1)
            set_path(p_data if scope == "profile" else m_data, path, float(values[i]))
        p, m = type(profile).model_validate(p_data), type(cfg).model_validate(m_data)
        result = analyse_site(market, site, p, m, region).result
        points, _ = project_site(result, market, p, m, region.metric_crs, calendar, open_date)
        revenue[i] = [pt.revenue for pt in points]
        rent = result.rent  # doesn't depend on the drawn parameters
    return SiteDraws(revenue, _profit(revenue, profile, rent))


# --- Summary ----------------------------------------------------------------------------------


def run_uncertainty(analyses: list[SiteAnalysis], components: list[MonthlyComponents],
                    market: Market, profile: BusinessProfile, cfg: ModelConfig, region: Region,
                    calendar: Calendar, open_date: dt.date, n_runs: int | None = None
                    ) -> Uncertainty:
    mc = cfg.montecarlo
    n = n_runs or mc.n_runs
    draws, base = sample_parameters(cfg, profile, n, mc.seed)
    if mc.mode == "fast":
        check_fast_supported(cfg)
        per_site = [fast_site_draws(a, c, market, profile, cfg, draws, base, n)
                    for a, c in zip(analyses, components, strict=True)]
    else:
        per_site = [full_site_draws(market, a.result.site, profile, cfg, region, calendar,
                                    open_date, draws, n) for a in analyses]

    lo, mid, hi = mc.percentiles
    totals = np.column_stack([d.revenue.sum(axis=1) for d in per_site])   # (n, sites)
    best = totals == totals.max(axis=1, keepdims=True)
    best = best / best.sum(axis=1, keepdims=True)                         # split ties
    sites = []
    for j, (a, d) in enumerate(zip(analyses, per_site, strict=True)):
        q = np.percentile(d.revenue, [lo, mid, hi], axis=0)
        t = np.percentile(totals[:, j], [lo, mid, hi])
        profit_totals = d.profit.sum(axis=1) if d.profit is not None else None
        sites.append(SiteUncertainty(
            site_id=a.result.site.id,
            revenue=Band(p10=q[0].tolist(), p50=q[1].tolist(), p90=q[2].tolist()),
            total_revenue={"p10": float(t[0]), "p50": float(t[1]), "p90": float(t[2])},
            total_profit=None if profit_totals is None else dict(zip(
                ("p10", "p50", "p90"), map(float, np.percentile(profit_totals, [lo, mid, hi])),
                strict=True)),
            prob_best=float(best[:, j].mean()),
            prob_loss=None if profit_totals is None else float((profit_totals < 0).mean()),
        ))
    return Uncertainty(
        n_runs=n, mode=mc.mode, seed=mc.seed, percentiles=list(mc.percentiles),
        parameters=[ParameterRange(path=k, base=base[k],
                                   p10=float(np.percentile(v, lo)), p90=float(np.percentile(v, hi)))
                    for k, v in draws.items()],
        sites=sites,
    )
