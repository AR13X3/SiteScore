"""Matching the same business across sources by name and location."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

# Words too generic to identify a business on their own.
GENERIC = {"cafe", "caf", "coffee", "the", "and", "co", "espresso", "kitchen", "bar", "shop",
           "house", "roasters", "eatery", "restaurant", "pty", "ltd", "gym", "fitness",
           "childcare", "child", "care", "centre", "center", "early", "learning"}


def normalise_name(name: str) -> str:
    """'Nadia’s Café & Co.' -> 'nadias cafe co' (accents and punctuation removed)."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    text = re.sub(r"['’`]", "", text.lower())
    return " ".join(re.findall(r"[a-z0-9]+", text))


def name_tokens(name: str) -> set[str]:
    words = set(normalise_name(name).split())
    return (words - GENERIC) or words


def same_business(a: str, b: str) -> bool:
    """Do two names plausibly refer to the same business?

    True for shared distinctive words ('XS' / 'XS Espresso') or near-identical
    spellings ('Picollo Me' / 'Piccolo Me'); False for 'Koko n Beans' / 'XA Expresso'.
    """
    if name_tokens(a) & name_tokens(b):
        return True
    return SequenceMatcher(None, normalise_name(a), normalise_name(b)).ratio() >= 0.8


def distance_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Approximate metres between points (fine at city scale)."""
    return np.hypot((np.asarray(lon2) - lon1) * 92_600, (np.asarray(lat2) - lat1) * 110_500)


def best_match(name: str, lat: float, lon: float, candidates: pd.DataFrame,
               max_m: float = 100, name_col: str = "name") -> pd.Series | None:
    """Nearest candidate within max_m sharing a distinctive name word, else None."""
    if candidates is None or candidates.empty:
        return None
    d = distance_m(lat, lon, candidates["lat"].to_numpy(float), candidates["lon"].to_numpy(float))
    near = candidates.assign(_d=d)[d <= max_m]
    if near.empty:
        return None
    same = near[[same_business(name, n) for n in near[name_col].fillna("")]]
    return None if same.empty else same.sort_values("_d").iloc[0].drop(labels="_d")
