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
