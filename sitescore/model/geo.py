"""Projection and walking distances."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from pyproj import Transformer

from sitescore.config import DistanceCfg


@lru_cache
def _transformer(crs: str) -> Transformer:
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def project(lon, lat, crs: str) -> tuple[np.ndarray, np.ndarray]:
    """WGS84 lon/lat -> metres in the region's projected CRS."""
    x, y = _transformer(crs).transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    return np.asarray(x), np.asarray(y)


def walk_distance(x0, y0, x, y, cfg: DistanceCfg, floor: bool = True) -> np.ndarray:
    """Approximate walking distance: straight line x detour factor.

    floor=True applies min_distance_m (for choice models); use floor=False for
    distances shown to people. Broadcasts: (n,1) against (1,k) gives n x k.
    """
    walk = np.hypot(np.asarray(x) - x0, np.asarray(y) - y0) * cfg.detour_factor
    return np.maximum(walk, cfg.min_distance_m) if floor else walk


def minutes_to_metres(minutes: float, cfg: DistanceCfg) -> float:
    return minutes * cfg.walk_speed_kmh * 1000 / 60
