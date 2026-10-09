"""Layer 6: time dynamics. Mature monthly revenue -> a month-by-month path.

    visits(t) = ramp(t) x [ sum over segments of mature visits x seasonal(t, segment)
                            + visits from residents of new developments(t) ]
    capped at capacity each month, then x average transaction value.

- Ramp: a new store starts at ramp_start_share of mature trade and closes 90% of
  the gap by ramp_months_to_90pct (exponential approach).
- Seasonal: the profile's monthly pattern x school-holiday effect per segment,
  normalised so a calendar year averages 1 (mature = average month).
- Developments: DAs approved as of the run date add residents when they're
  expected to complete (approval + build time by size), filling up gradually.
  Only completions after the Census date count; earlier ones are in the Census.
"""

from __future__ import annotations

import calendar as cal
import datetime as dt
import math

import numpy as np
import pandas as pd

from sitescore.config import SEGMENTS, BusinessProfile, Calendar, Dynamics, ModelConfig
from sitescore.model.demand import reach, time_alignment
from sitescore.model.fit import area_multipliers
from sitescore.model.geo import minutes_to_metres, project, walk_distance
from sitescore.model.huff import huff_probabilities
from sitescore.model.market import Market
from sitescore.model.spend import monthly_profit
from sitescore.model.types import LayerResult, MonthPoint, Site, SiteResult


def month_starts(open_date: dt.date, n: int) -> list[dt.date]:
    start = dt.date(open_date.year, open_date.month, 1)
    return [d.date() for d in pd.date_range(start, periods=n, freq="MS")]


def ramp_curve(n: int, dyn: Dynamics) -> np.ndarray:
    s = dyn.ramp_start_share
    if s >= 0.9:
        return np.ones(n)
    k = math.log((1 - s) / 0.1) / dyn.ramp_months_to_90pct
    return 1 - (1 - s) * np.exp(-k * np.arange(n))


def seasonal_factors(months: list[dt.date], profile: BusinessProfile, calendar: Calendar
                     ) -> dict[str, np.ndarray]:
    """Per-segment multiplier for each month; each averages 1 over a calendar year."""
    season = np.array(profile.dynamics.seasonality)
    holidays = np.array([calendar.school_holiday_fraction[m] for m in range(1, 13)])
    idx = np.array([d.month for d in months]) - 1
    out = {}
    for seg in SEGMENTS:
        year = season * (1 + profile.dynamics.school_holiday_effect[seg] * holidays)
        out[seg] = (year / year.mean())[idx]
    return out


def development_schedule(market: Market, cfg: ModelConfig) -> pd.DataFrame:
    """Approved DAs with expected completion dates, if they complete after the Census."""
    dev = market.developments.copy()
    if dev.empty:
        return dev.assign(completion=pd.Series(dtype="datetime64[ns]"))
    buckets = sorted(cfg.developments.build_months, key=lambda b: b.max_dwellings)

    def build_months(n: float) -> int:
        return next(b.months for b in buckets if n <= b.max_dwellings)

    months = dev["new_dwellings"].map(build_months)
    dev["completion"] = [pd.Timestamp(a) + pd.DateOffset(months=int(m))
                         for a, m in zip(dev["approved"], months, strict=True)]
    return dev[dev["completion"] > pd.Timestamp(market.census_date)].reset_index(drop=True)


def new_residents(schedule: pd.DataFrame, months: list[dt.date], cfg: ModelConfig) -> np.ndarray:
    """Residents living in each development (rows) in each month (columns)."""
    if schedule.empty:
        return np.zeros((0, len(months)))
    t = np.array([pd.Timestamp(m).value for m in months], dtype=float)
    done = schedule["completion"].map(lambda c: pd.Timestamp(c).value).to_numpy(float)
    months_since = (t[None, :] - done[:, None]) / (30.44 * 86400e9)
    ramp = cfg.developments.occupancy_ramp_months
    occupied = (np.clip(months_since / ramp, 0, 1) if ramp > 0
                else (months_since >= 0).astype(float))
    people = schedule["new_dwellings"].to_numpy(float) * cfg.developments.persons_per_new_dwelling
    return people[:, None] * occupied


def visits_per_new_resident(sx: float, sy: float, schedule: pd.DataFrame, market: Market,
                            profile: BusinessProfile, cfg: ModelConfig, anchor_factor: float
                            ) -> np.ndarray:
    """Monthly visits to our site per person living in each development.

    Same chain as existing residents: reach x participation x time alignment x
    local fit x competitive share x visit frequency, with the development borrowing
    fit and population mix from the nearest existing small area.
    """
    if schedule.empty or not len(market.residents):
        return np.zeros(len(schedule))
    spec = profile.segments["residents"]
    x, y = schedule["x"].to_numpy(float), schedule["y"].to_numpy(float)
    radius = minutes_to_metres(spec.max_walk_minutes, cfg.distance)
    r = reach(walk_distance(sx, sy, x, y, cfg.distance, floor=False), radius,
              cfg.distance.catchment_fade)

    nearest = np.argmin((x[:, None] - market.residents.x[None, :]) ** 2
                        + (y[:, None] - market.residents.y[None, :]) ** 2, axis=1)
    fit = area_multipliers(market, profile)[nearest] if spec.fit_applies else 1.0
    scale = (market.resident_features[spec.population_scale].to_numpy(float)[nearest]
             if spec.population_scale else 1.0)

    h, comp = cfg.huff, market.competitors
    d_own = walk_distance(sx, sy, x, y, cfg.distance)
    d_comp = walk_distance(x[:, None], y[:, None], comp.x[None, :], comp.y[None, :], cfg.distance)
    p_own, _, _ = huff_probabilities(d_own, d_comp, profile.our_store.attractiveness, comp.weight,
                                     h.alpha, h.beta, h.outside_option.attractiveness,
                                     h.outside_option.distance_m)
    tau = time_alignment(profile)["residents"]
    return (r * spec.participation * tau * fit * scale * p_own * anchor_factor
            * spec.visits_per_month)


def project_site(result: SiteResult, market: Market, profile: BusinessProfile, cfg: ModelConfig,
                 region_crs: str, calendar: Calendar, open_date: dt.date
                 ) -> tuple[list[MonthPoint], LayerResult]:
    n = cfg.horizon_months
    months = month_starts(open_date, n)
    # Agent-simulated ramp when available (awareness + habits), else the profile curve.
    ramp = np.array(result.ramp[:n]) if result.ramp else ramp_curve(n, profile.dynamics)
    seasonal = seasonal_factors(months, profile, calendar)
    base = sum(result.segment_visits.get(seg, 0.0) * seasonal[seg] for seg in SEGMENTS)

    site: Site = result.site
    xs, ys = project([site.lon], [site.lat], region_crs)
    factor = {layer.key: layer.factor for layer in result.layers}
    # New residents get the same anchor boost and agent/price effects as existing ones.
    uplift = factor.get("anchors", 1.0) * factor.get("behaviour", 1.0) * factor.get("price", 1.0)
    schedule = development_schedule(market, cfg)
    coef = visits_per_new_resident(float(xs[0]), float(ys[0]), schedule, market, profile, cfg,
                                   uplift)
    residents = new_residents(schedule, months, cfg)
    dev = (coef @ residents) * seasonal["residents"] if len(coef) else np.zeros(n)

    uncapped = (base + dev) * ramp
    cap = profile.spend.capacity_visits_per_month
    visits = np.minimum(uncapped, cap) if cap else uncapped
    kept = np.divide(visits, uncapped, out=np.ones(n), where=uncapped > 0)
    atv = result.avg_transaction_value
    revenue = visits * atv
    dev_revenue = dev * ramp * kept * atv

    points = [MonthPoint(month=m, revenue=float(revenue[i]), visits=float(visits[i]),
                         profit=monthly_profit(float(revenue[i]), profile.costs),
                         development_revenue=float(dev_revenue[i]))
              for i, m in enumerate(months)]
    return points, _dynamics_layer(result, revenue, dev_revenue, ramp, seasonal, months, schedule,
                                   coef, residents, profile, n)


def _dynamics_layer(result: SiteResult, revenue: np.ndarray, dev_revenue: np.ndarray,
                    ramp: np.ndarray, seasonal: dict, months: list[dt.date],
                    schedule: pd.DataFrame, coef: np.ndarray, residents: np.ndarray,
                    profile: BusinessProfile, n: int) -> LayerResult:
    mature = result.monthly_revenue
    factor = float(revenue.sum() / (n * mature)) if mature > 0 else 1.0

    combined = sum(result.segment_visits.get(s, 0.0) * seasonal[s] for s in SEGMENTS)
    total_visits = sum(result.segment_visits.values())
    season = combined / total_visits if total_visits > 0 else np.ones(n)
    low = int(np.argmin(season[:12]))

    added = coef[:, None] * residents if len(coef) else np.zeros((0, n))
    in_reach = added[:, -1] > 0  # contributes visits by the end of the horizon
    top = np.argsort(-added[:, -1])[:5] if len(coef) else []
    developments = [
        {"da_id": str(schedule["da_id"].iat[i]),
         "new_dwellings": int(schedule["new_dwellings"].iat[i]),
         "approved": str(pd.Timestamp(schedule["approved"].iat[i]).date()),
         "expected_completion": str(pd.Timestamp(schedule["completion"].iat[i]).date()),
         "visits_per_month_at_end": round(float(added[i, -1]))}
        for i in top if added[i, -1] > 0.5
    ]
    years = [float(revenue[i:i + 12].sum()) for i in range(0, n, 12)]
    reached = np.flatnonzero(ramp >= 0.9)
    to_90 = f"90% by month {reached[0] + 1}" if len(reached) else f"{ramp[-1]:.0%} by month {n}"
    parts = [f"Ramp-up from {ramp[0]:.0%} of mature trade in month 1 to {to_90}",
             f"seasonal low in {cal.month_name[months[low].month]} ({season[low] - 1:+.0%})"]
    if dev_revenue[-1] > 1:
        parts.append(f"{int(in_reach.sum())} approved developments in reach add "
                     f"${dev_revenue[-1]:,.0f}/month by month {n}")
    return LayerResult(
        key="time", label="Ramp-up, seasons & growth", factor=factor, unit="x",
        summary="; ".join(parts),
        details={"ramp": [round(float(r), 3) for r in ramp],
                 "yearly_revenue": [round(y) for y in years],
                 "developments_in_reach": int(in_reach.sum()),
                 "top_developments": developments},
    )
