"""Accuracy measures for predicted vs actual rankings (small cohorts friendly)."""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import spearmanr

# Nested versions of the model, each adding layers to the one before. Revenue is an
# exact product of layer factors, so each rung is the model with the later layers
# switched off (e.g. "+ competition" is plain Huff, before agents and prices).
LADDER: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("demand", "Foot traffic only", ("demand",)),
    ("location", "+ demographic fit and anchors", ("fit", "anchors")),
    ("competition", "+ competition (Huff)", ("competition",)),
    ("agents", "+ customer agents", ("behaviour",)),
    ("price", "+ competitors' price response", ("price",)),
    ("full", "Full model (+ spend, capacity)", ("spend", "capacity")),
)
# Scores that aren't a product of layers, compared alongside the ladder.
EXTRA_RUNGS = {"profit": "Profit, after site-specific rent"}


def pairwise_accuracy(pred: np.ndarray, actual: np.ndarray) -> tuple[float | None, int]:
    """Share of pairs the model orders the same way as reality (ties in pred = half).

    Only pairs whose actual outcomes differ count. 0.5 = coin flip.
    """
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    upper = np.triu_indices(len(pred), k=1)
    a = np.sign(actual[:, None] - actual[None, :])[upper]
    p = np.sign(pred[:, None] - pred[None, :])[upper]
    differ = a != 0
    pairs = int(differ.sum())
    if not pairs:
        return None, 0
    good = (p[differ] == a[differ]).sum() + 0.5 * (p[differ] == 0).sum()
    return float(good / pairs), pairs


def spearman(pred: np.ndarray, actual: np.ndarray) -> float | None:
    if len(pred) < 3 or np.ptp(actual) == 0 or np.ptp(pred) == 0:
        return None
    return float(spearmanr(pred, actual).statistic)


def survival_auc(pred: np.ndarray, still_open: np.ndarray) -> float | None:
    """Chance a random survivor was predicted higher than a random closure."""
    pred, alive = np.asarray(pred, float), np.asarray(still_open, bool)
    if alive.all() or not alive.any():
        return None
    a, c = pred[alive], pred[~alive]
    wins = (a[:, None] > c[None, :]).sum() + 0.5 * (a[:, None] == c[None, :]).sum()
    return float(wins / (len(a) * len(c)))


def thirds(pred: np.ndarray, actual: np.ndarray) -> tuple[float | None, float | None]:
    """Average actual percentile (0-100) of the top and bottom third by prediction."""
    n = len(pred)
    if n < 3:
        return None, None
    actual_pct = (np.argsort(np.argsort(actual)) / (n - 1)) * 100
    order = np.argsort(-np.asarray(pred, float))
    k = max(1, n // 3)
    return float(actual_pct[order[:k]].mean()), float(actual_pct[order[-k:]].mean())


def thirds_index(pred: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Row indices of the top, middle and bottom third by prediction (sizes differ by <= 1)."""
    order = np.argsort(-np.asarray(pred, float), kind="stable")
    return list(zip(("top", "middle", "bottom"), np.array_split(order, 3), strict=True))


def closure_by_third(pred: np.ndarray, status: np.ndarray, failure: np.ndarray,
                     site_closures: np.ndarray) -> list[dict]:
    """Closure rate at the horizon within each predicted third.

    status: closed / survived / censored / unknown per business; only closed and
    survived are judged. failure: operator / site / unknown for closures.
    """
    rows = []
    for name, idx in thirds_index(pred):
        st, fail = status[idx], failure[idx]
        judged = int(np.isin(st, ["closed", "survived"]).sum())
        closed = int((st == "closed").sum())
        rows.append({
            "third": name, "n": len(idx), "judged": judged, "closed": closed,
            "closure_rate": closed / judged if judged else None,
            "site_failures": int(((st == "closed") & (fail == "site")).sum()),
            "operator_failures": int(((st == "closed") & (fail == "operator")).sum()),
            "mean_site_closures": float(site_closures[idx].mean()) if len(idx) else None,
        })
    return rows


def ladder_scores(layers: list[dict[str, float]], profit: np.ndarray | None = None
                  ) -> dict[str, np.ndarray]:
    """Each rung's score per business: the running product of its layer factors, plus
    profit after site-specific rent when available."""
    out, running = {}, np.ones(len(layers))
    for key, _, keys in LADDER:
        running = running * np.array([math.prod(lay.get(k, 1.0) for k in keys) for lay in layers])
        out[key] = running
    if profit is not None and len(profit) and not np.isnan(np.asarray(profit, float)).any():
        out["profit"] = np.asarray(profit, float)
    return out


def ladder_comparison(scores: dict[str, np.ndarray], outcome: np.ndarray, n_boot: int = 500,
                      seed: int = 0) -> list[dict]:
    """How well each rung ranks an outcome (higher = better), with 90% bootstrap
    intervals for its Spearman and for its gain over foot traffic only.

    The intervals resample businesses, so they show how much a result could move
    with a different sample of the same size; they say nothing about bias.
    """
    ok = ~np.isnan(np.asarray(outcome, float))
    y = np.asarray(outcome, float)[ok]
    n = len(y)
    boot = np.random.default_rng(seed).integers(0, n, size=(n_boot, n)) if n >= 10 else None
    base = scores[LADDER[0][0]][ok]
    base_boot = _boot_spearman(base, y, boot)
    rows = []
    rungs = [(k, label) for k, label, _ in LADDER] + [
        (k, label) for k, label in EXTRA_RUNGS.items() if k in scores]
    for key, label in rungs:
        s = scores[key][ok]
        pw, pairs = pairwise_accuracy(s, y)
        rho_boot = _boot_spearman(s, y, boot)
        rows.append({
            "key": key, "label": label, "n": n, "pairs": pairs, "pairwise_accuracy": pw,
            "spearman": spearman(s, y),
            "spearman_ci": _interval(rho_boot),
            "gain_ci": None if key == LADDER[0][0] else _interval(rho_boot - base_boot),
        })
    return rows


def _boot_spearman(s: np.ndarray, y: np.ndarray, boot: np.ndarray | None) -> np.ndarray:
    if boot is None:
        return np.array([])
    return np.array([spearman(s[i], y[i]) if np.ptp(y[i]) and np.ptp(s[i]) else np.nan
                     for i in boot], dtype=float)


def _interval(draws: np.ndarray) -> tuple[float, float] | None:
    draws = draws[~np.isnan(draws)]
    if len(draws) < 50:
        return None
    lo, hi = np.percentile(draws, [5, 95])
    return float(lo), float(hi)


def compare_outcome(key: str, label: str, scores: dict[str, np.ndarray],
                    outcome: np.ndarray | None, missing: str) -> dict:
    """The ladder against one outcome, or why it can't be compared (OutcomeComparison)."""
    y = None if outcome is None else np.asarray(outcome, float)
    ok = np.zeros(0, bool) if y is None else ~np.isnan(y)
    if y is None or ok.sum() < 3:
        return {"outcome": key, "label": label, "available": False, "note": missing, "steps": []}
    if np.ptp(y[ok]) == 0:
        return {"outcome": key, "label": label, "available": False,
                "note": "no variation in this outcome", "steps": []}
    return {"outcome": key, "label": label, "available": True, "note": "",
            "steps": ladder_comparison(scores, y)}
