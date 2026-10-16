"""Find the best spots inside an area the user draws.

1. Candidates: the vacant shopfronts in the circle, or a grid over it (optionally
   only near where similar businesses already trade, i.e. real shopping strips,
   where a shopfront to lease is plausible; schools and hospitals don't count).
2. Quick score for every candidate: the model with the agents and the price game
   switched off (demand x fit x anchors x Huff share x spend), about 2 ms each.
3. Shortlist: the best quick scores, kept at least min_separation_m apart so the
   suggestions don't all pile onto one busy corner.
4. The shortlist runs through the full model over 36 months and is ranked by
   revenue or profit; the top results get Monte Carlo ranges.

Ranking by profit uses each site's estimated rent (model/rent.py), so a busy
corner with a high rent can rank below a quieter, cheaper one.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from sitescore.config import BusinessProfile, Calendar, ModelConfig, Region
from sitescore.model.geo import project
from sitescore.model.market import Market
from sitescore.model.simulate import simulate
from sitescore.model.site import analyse_site
from sitescore.model.types import SimulationResult, Site

RankBy = Literal["revenue", "profit"]


@dataclass(frozen=True)
class Area:
    lat: float
    lon: float
    radius_m: float


@dataclass(frozen=True)
class Candidate:
    id: str
    lat: float
    lon: float
    label: str
    kind: str              # "Location", "Vacant shop", "Former café"...
    former_use: str = ""


@dataclass
class SpotSearch:
    candidates: list[Candidate]
    quick: np.ndarray           # quick-score monthly revenue (or profit) per candidate
    shortlisted: list[str]      # candidate ids re-run with the full model
    top: SimulationResult | None
    labels: dict[str, Candidate]


def metres(lat0: float, lon0: float, lat, lon) -> np.ndarray:
    """Equirectangular distance in metres (fine across a few km)."""
    kx = 111_320 * math.cos(math.radians(lat0))
    return np.hypot((np.asarray(lon) - lon0) * kx, (np.asarray(lat) - lat0) * 110_574)


def in_area(area: Area, lat, lon) -> np.ndarray:
    return metres(area.lat, area.lon, lat, lon) <= area.radius_m


def grid_candidates(area: Area, market: Market, region: Region, cfg: ModelConfig,
                    retail_only: bool = True) -> list[Candidate]:
    """Grid points in the circle (inside the region), spacing adapted to its size."""
    s = cfg.search
    spacing = max(s.min_spacing_m, area.radius_m * math.sqrt(math.pi / s.grid_points))
    dlat = spacing / 110_574
    dlon = spacing / (111_320 * math.cos(math.radians(area.lat)))
    n = int(area.radius_m // spacing) + 1
    lat = area.lat + dlat * np.arange(-n, n + 1)
    lon = area.lon + dlon * np.arange(-n, n + 1)
    glat, glon = (a.ravel() for a in np.meshgrid(lat, lon, indexing="ij"))
    lon0, lat0, lon1, lat1 = region.bbox
    keep = in_area(area, glat, glon) & (glon >= lon0) & (glon <= lon1) & (glat >= lat0) & (glat <= lat1)
    if retail_only:
        vlat, vlon = market.competitors.lat, market.competitors.lon
        near = np.zeros(len(glat), bool)
        for i in np.flatnonzero(keep):
            near[i] = (metres(glat[i], glon[i], vlat, vlon) <= s.retail_within_m).any()
        keep &= near
    return [Candidate(f"grid-{i}", float(glat[i]), float(glon[i]), nearest_label(market, glat[i], glon[i]),
                      "Location") for i in np.flatnonzero(keep)]


def hex_candidates(market: Market, region: Region, cfg: ModelConfig) -> list[Candidate]:
    """Centres of a hex grid over the region's bounding box (rows offset by half a cell),
    minus cells with no residents or workers within reach (parks, water, rail yards)."""
    s = cfg.search
    lon0, lat0, lon1, lat1 = region.bbox
    dlat = s.heatmap_spacing_m * math.sqrt(3) / 2 / 110_574
    dlon = s.heatmap_spacing_m / (111_320 * math.cos(math.radians((lat0 + lat1) / 2)))
    rows = np.arange(lat0, lat1 + dlat / 2, dlat)
    glat, glon = [], []
    for r, lat in enumerate(rows):
        lons = np.arange(lon0 + (dlon / 2 if r % 2 else 0), lon1 + dlon / 2, dlon)
        glat.append(np.full(len(lons), lat))
        glon.append(lons)
    glat, glon = np.concatenate(glat), np.concatenate(glon)
    x, y = project(glon, glat, region.metric_crs)
    people = [p for p in (market.residents, market.workers) if len(p)]
    near = np.zeros(len(x), bool)
    if people:
        px = np.concatenate([p.x for p in people])
        py = np.concatenate([p.y for p in people])
        for i in range(0, len(x), 256):  # chunked: cells x people distances stay small
            d = np.hypot(x[i:i + 256, None] - px[None, :], y[i:i + 256, None] - py[None, :])
            near[i:i + 256] = d.min(axis=1) <= s.heatmap_near_people_m
    return [Candidate(f"hex-{i}", float(glat[i]), float(glon[i]), "", "Location")
            for i in np.flatnonzero(near)]


def nearest_label(market: Market, lat: float, lon: float, within_m: float = 300) -> str:
    """'Near Westfield Parramatta': the closest named anchor, else café, within reach."""
    for venues in (market.anchors, market.competitors):
        named = np.array([bool(n) for n in venues.names], bool)
        if not named.any():
            continue
        d = metres(lat, lon, venues.lat[named], venues.lon[named])
        i = int(np.argmin(d))
        if d[i] <= within_m:
            return f"Near {venues.names[named][i]}"
    return f"Spot at {lat:.4f}, {lon:.4f}"


def quick_scores(market: Market, candidates: list[Candidate], profile: BusinessProfile,
                 cfg: ModelConfig, region: Region, rank_by: RankBy = "revenue") -> np.ndarray:
    """Mature monthly revenue (or profit, with the site's rent) with agents and the
    price game switched off."""
    fast = cfg.model_copy(update={"abm": cfg.abm.model_copy(update={"enabled": False}),
                                  "game": cfg.game.model_copy(update={"enabled": False})})
    out = []
    for c in candidates:
        r = analyse_site(market, Site(id=c.id, label=c.label, lat=c.lat, lon=c.lon), profile,
                         fast, region).result
        out.append(r.monthly_profit if rank_by == "profit" and r.monthly_profit is not None
                   else r.monthly_revenue)
    return np.array(out, dtype=float)


def spread(order: np.ndarray, lat: np.ndarray, lon: np.ndarray, k: int, min_sep_m: float
           ) -> list[int]:
    """Greedy: take the best remaining candidate at least min_sep_m from those taken."""
    taken: list[int] = []
    for i in order:
        if all(metres(lat[i], lon[i], lat[j], lon[j]) >= min_sep_m for j in taken):
            taken.append(int(i))
            if len(taken) == k:
                break
    return taken


def find_spots(market: Market, candidates: list[Candidate], profile: BusinessProfile,
               cfg: ModelConfig, region: Region, calendar: Calendar,
               rank_by: RankBy = "revenue", open_date: dt.date | None = None,
               n_runs: int | None = None, min_separation_m: float | None = None) -> SpotSearch:
    """min_separation_m: defaults to the config's; 0 for real premises (vacant shopfronts
    are distinct even when they're next door to each other)."""
    labels = {c.id: c for c in candidates}
    if not candidates:
        return SpotSearch([], np.array([]), [], None, labels)
    s = cfg.search
    sep = s.min_separation_m if min_separation_m is None else min_separation_m
    quick = quick_scores(market, candidates, profile, cfg, region, rank_by)
    lat = np.array([c.lat for c in candidates])
    lon = np.array([c.lon for c in candidates])
    short = spread(np.argsort(-quick, kind="stable"), lat, lon, s.shortlist, sep)
    sites = [Site(id=candidates[i].id, label=candidates[i].label, lat=candidates[i].lat,
                  lon=candidates[i].lon) for i in short]
    # One pass: every shortlisted spot over 36 months, ranges for the best few.
    full = simulate(market, sites, profile, cfg, region, calendar, open_date,
                    uncertainty=True, n_runs=n_runs, uncertainty_top=s.results,
                    uncertainty_by=rank_by)
    return SpotSearch(candidates, quick, [candidates[i].id for i in short], full, labels)
