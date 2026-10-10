"""Matching the same business across sources by name and location."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

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


@lru_cache
def place_words() -> frozenset[str]:
    """Suburb and street words for the region (config/regions/<id>.yaml)."""
    from sitescore.config import load_region  # late: config isn't needed for plain matching
    try:
        return frozenset(load_region().place_words)
    except FileNotFoundError:
        return frozenset()


def name_tokens(name: str) -> set[str]:
    """Distinctive words: without generic words, and without place words when the
    name has others ('Cotti Coffee (Parramatta)' -> {'cotti'}, 'Parramatta Cafe' ->
    {'parramatta'})."""
    words = set(normalise_name(name).split())
    rest = words - GENERIC
    return (rest - place_words()) or rest or words


def compact_name(name: str) -> str:
    """Distinctive words run together: 'Cafe Long Shot' -> 'longshot'."""
    words, keep = normalise_name(name).split(), name_tokens(name)
    return "".join(w for w in words if w in keep)


def same_business(a: str, b: str) -> bool:
    """Do two names plausibly refer to the same business?

    True for shared distinctive words ('XS' / 'XS Espresso'), near-identical
    spellings ('Picollo Me' / 'Piccolo Me') or the same words spaced differently
    ('Longshot Cafe' / 'Cafe Long Shot', 'Meet Fresh' / 'MeetFresh Eastwood');
    False for 'Koko n Beans' / 'XA Expresso'.
    """
    if name_tokens(a) & name_tokens(b):
        return True
    ca, cb = compact_name(a), compact_name(b)
    short, long_ = sorted((ca, cb), key=len)
    if len(short) >= 6 and long_.startswith(short):
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
