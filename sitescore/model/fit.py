"""Layer 2: demographic fit. How well local residents match the customer profile.

Each feature is z-scored against the whole region (population-weighted), so 0
means "region average". Per small area:

    index      = sum(w_f * z_f) / sum(|w_f|)      (weights from the business YAML)
    multiplier = clip(exp(strength * index))

Only segments with fit_applies (residents, by default) are adjusted: workers and
commuters are characterised by where they work or travel, not where they live.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sitescore.config import BusinessProfile
from sitescore.features import FEATURES
from sitescore.model.demand import Catchment
from sitescore.model.market import Market


@dataclass(frozen=True)
class FitResult:
    point_multiplier: np.ndarray  # per catchment point; 1 where fit doesn't apply
    factor: float                 # demand-weighted mean multiplier over the catchment
    residents_multiplier: float
    index: float                  # catchment's fit index (sum of contributions)
    contributions: list[dict]     # per feature, sorted by absolute impact


def region_zscores(features: pd.DataFrame, population: np.ndarray, names: list[str]
                   ) -> pd.DataFrame:
    w = np.asarray(population, dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1 / max(len(w), 1))
    out = {}
    for name in names:
        v = features[name].to_numpy(float)
        mean = float(np.sum(w * v))
        sd = float(np.sqrt(np.sum(w * (v - mean) ** 2)))
        out[name] = (v - mean) / sd if sd > 0 else np.zeros_like(v)
    return pd.DataFrame(out)


def compute_fit(catchment: Catchment, market: Market, profile: BusinessProfile) -> FitResult:
    names = list(profile.fit.features)
    raw = np.array([profile.fit.features[n].weight for n in names])
    weights = raw / np.abs(raw).sum() if np.abs(raw).any() else raw
    z_all = region_zscores(market.resident_features, market.residents.people, names)

    mult = np.ones(len(catchment.weight))
    is_res = (catchment.segment == "residents") & catchment.fit_applies
    res_rows = catchment.source_index[is_res]
    z = z_all.to_numpy()[res_rows] if len(res_rows) else np.zeros((0, len(names)))
    index_pts = z @ weights if len(names) else np.zeros(len(res_rows))
    lo, hi = profile.fit.clip
    mult[is_res] = np.clip(np.exp(profile.fit.strength * index_pts), lo, hi)

    w = catchment.weight
    total = w.sum()
    factor = float((w * mult).sum() / total) if total > 0 else 1.0
    res_w = w[is_res]
    res_mult = float((res_w * mult[is_res]).sum() / res_w.sum()) if res_w.sum() > 0 else 1.0
    zbar = (res_w @ z / res_w.sum()) if res_w.sum() > 0 else np.zeros(len(names))

    contributions = sorted(
        ({"feature": n, "description": FEATURES[n], "why": profile.fit.features[n].why,
          "weight": float(weights[i]), "catchment_z": round(float(zbar[i]), 3),
          "contribution": round(float(weights[i] * zbar[i]), 4)}
         for i, n in enumerate(names)),
        key=lambda c: -abs(c["contribution"]),
    )
    return FitResult(mult, factor, res_mult, float(weights @ zbar), contributions)
