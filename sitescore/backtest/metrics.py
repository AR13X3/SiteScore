"""Accuracy measures for predicted vs actual rankings (small cohorts friendly)."""

from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr


def pairwise_accuracy(pred: np.ndarray, actual: np.ndarray) -> tuple[float | None, int]:
    """Share of pairs the model orders the same way as reality (ties in pred = half).

    Only pairs whose actual outcomes differ count. 0.5 = coin flip.
    """
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    good, pairs = 0.0, 0
    for i in range(len(pred)):
        for j in range(i + 1, len(pred)):
            a = np.sign(actual[i] - actual[j])
            if a == 0:
                continue
            pairs += 1
            p = np.sign(pred[i] - pred[j])
            good += 1.0 if p == a else 0.5 if p == 0 else 0.0
    return (good / pairs if pairs else None), pairs


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
