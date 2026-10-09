"""A synthetic city for mock data.

All mock adapters draw from the same fake geography, so mock residents, workers,
stations, cafés and developments are spatially consistent: cafés cluster where
the jobs are, apartments sit near the centres, and so on. That gives the model
real structure to find even when every source is mocked.

Centre locations and station names follow the real City of Parramatta so the map
looks familiar; every number attached to them is invented. Nothing here is a
model assumption: these are only used when real data is unavailable.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from sitescore.config import Region


@dataclass(frozen=True)
class Centre:
    name: str
    lat: float
    lon: float
    residents: float   # relative residential density
    jobs: float        # relative job density
    apartments: float  # 0..1 apartment intensity at the core
    radius_m: float


CENTRES: tuple[Centre, ...] = (
    Centre("Parramatta CBD", -33.8150, 151.0030, 1.0, 1.00, 0.90, 900),
    Centre("Westmead", -33.8070, 150.9880, 0.6, 0.70, 0.50, 700),
    Centre("Harris Park", -33.8226, 151.0079, 0.8, 0.10, 0.70, 600),
    Centre("Granville", -33.8326, 151.0123, 0.6, 0.15, 0.50, 700),
    Centre("Epping", -33.7727, 151.0820, 0.7, 0.25, 0.70, 700),
    Centre("Carlingford", -33.7820, 151.0480, 0.5, 0.05, 0.40, 900),
    Centre("Sydney Olympic Park", -33.8470, 151.0687, 0.4, 0.40, 0.80, 700),
    Centre("Wentworth Point", -33.8290, 151.0750, 0.7, 0.05, 0.95, 500),
    Centre("Rydalmere", -33.8120, 151.0330, 0.3, 0.45, 0.20, 800),
    Centre("North Rocks", -33.7730, 151.0130, 0.4, 0.05, 0.10, 1000),
    Centre("Ermington", -33.8150, 151.0560, 0.4, 0.05, 0.20, 900),
    Centre("Winston Hills", -33.7770, 150.9800, 0.4, 0.02, 0.05, 1000),
    Centre("Dundas", -33.7990, 151.0410, 0.5, 0.03, 0.30, 800),
    Centre("Melrose Park", -33.8130, 151.0720, 0.3, 0.10, 0.60, 500),
)


@dataclass(frozen=True)
class Station:
    name: str
    lat: float
    lon: float
    monthly_exits: float  # invented pre-COVID level
    mode: str = "train"
    opened: dt.date | None = None
    closed: dt.date | None = None


STATIONS: tuple[Station, ...] = (
    Station("Parramatta", -33.8170, 151.0050, 1_150_000),
    Station("Westmead", -33.8077, 150.9874, 330_000),
    Station("Harris Park", -33.8226, 151.0079, 140_000),
    Station("Granville", -33.8326, 151.0123, 260_000),
    Station("Wentworthville", -33.8073, 150.9719, 150_000),
    Station("Epping", -33.7727, 151.0820, 420_000),
    Station("Olympic Park", -33.8470, 151.0687, 90_000),
    # Heavy-rail stations closed for light-rail conversion; light rail opened Dec 2024.
    Station("Carlingford", -33.7822, 151.0489, 25_000, closed=dt.date(2020, 1, 5)),
    Station("Rydalmere", -33.8105, 151.0283, 20_000, closed=dt.date(2020, 1, 5)),
    Station("Parramatta Square Light Rail", -33.8155, 151.0035, 70_000, "light_rail",
            opened=dt.date(2024, 12, 20)),
    Station("Carlingford Light Rail", -33.7822, 151.0489, 20_000, "light_rail",
            opened=dt.date(2024, 12, 20)),
)


@dataclass(frozen=True)
class VenueKind:
    """A category of OSM point and how it evolves over time in the mock."""

    key: str
    tags: dict[str, str]
    initial: int                # count at the start of the simulation
    births_per_month: float = 0.0
    monthly_hazard: float = 0.0  # base closure probability per month
    job_mix: float = 0.5        # 1 = placed by job density, 0 = by resident density
    chain_share: float = 0.0
    brands: tuple[str, ...] = ()
    names: tuple[str, ...] = field(default_factory=tuple)


_CAFE_WORDS = ("Bean", "Grind", "Brew", "Crema", "Roast", "Daily", "Little", "Corner",
               "Laneway", "River", "Golden", "Common", "Sunday", "Kettle", "Ember", "Muse",
               "Juniper", "Olive", "Paper", "Copper", "Wattle", "Harbour", "Saint", "Neighbour")
_CAFE_SUFFIX = ("Espresso", "Coffee", "Café", "Kitchen", "& Co", "House", "Bar", "Roasters")

VENUE_KINDS: tuple[VenueKind, ...] = (
    VenueKind("cafe", {"amenity": "cafe"}, 125, 1.45, 0.0065, 0.65, 0.15,
              ("Gloria Jean's Coffees", "The Coffee Club", "Starbucks", "Muffin Break",
               "Michel's Patisserie", "Hudsons Coffee")),
    VenueKind("bakery", {"shop": "bakery"}, 35, 0.30, 0.0050, 0.30, 0.30,
              ("Bakers Delight", "Banjo's Bakery Cafe")),
    VenueKind("coffee_kiosk", {"amenity": "fast_food", "cuisine": "coffee_shop"}, 8, 0.10,
              0.0080, 0.70, 0.50, ("Gloria Jean's Coffees",)),
    VenueKind("supermarket", {"shop": "supermarket"}, 28, job_mix=0.2, chain_share=0.9,
              brands=("Woolworths", "Coles", "ALDI", "IGA")),
    VenueKind("school", {"amenity": "school"}, 60, job_mix=0.0, names=("School",)),
    VenueKind("university", {"amenity": "university"}, 3, job_mix=1.0, names=("University",)),
    VenueKind("hospital", {"amenity": "hospital"}, 2, job_mix=1.0, names=("Hospital",)),
    VenueKind("office", {"office": "company"}, 150, job_mix=1.0, names=("Office",)),
    VenueKind("gym", {"leisure": "fitness_centre"}, 35, 0.40, 0.0060, 0.50, 0.50,
              ("Anytime Fitness", "Snap Fitness", "F45 Training", "Jetts", "Fitness First")),
    VenueKind("sports_centre", {"leisure": "sports_centre"}, 12, job_mix=0.2,
              names=("Sports Centre",)),
    VenueKind("childcare", {"amenity": "childcare"}, 70, 0.60, 0.0040, 0.20, 0.40,
              ("Goodstart Early Learning", "Guardian Childcare & Education", "Little Zak's")),
    VenueKind("kindergarten", {"amenity": "kindergarten"}, 25, job_mix=0.1,
              names=("Preschool",)),
)

HISTORY_START = dt.date(2016, 1, 1)


class MockCity:
    def __init__(self, region: Region):
        lon_min, lat_min, lon_max, lat_max = region.bbox
        self.bbox = region.bbox
        self._lat0, self._lon0 = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
        self._kx = 111_320 * math.cos(math.radians(self._lat0))
        self._ky = 110_540.0
        cx, cy = self.xy(np.array([c.lat for c in CENTRES]), np.array([c.lon for c in CENTRES]))
        self._cx, self._cy = cx, cy
        self._radius = np.array([c.radius_m for c in CENTRES])
        self._weights = {
            kind: np.array([getattr(c, kind) for c in CENTRES])
            for kind in ("residents", "jobs", "apartments")
        }
        # Peak densities over the whole region, to normalise blends consistently.
        glat, glon = np.meshgrid(np.linspace(lat_min, lat_max, 120),
                                 np.linspace(lon_min, lon_max, 120))
        self._peak = {k: float(self.density(glat.ravel(), glon.ravel(), k).max())
                      for k in ("residents", "jobs")}

    # --- geometry --------------------------------------------------------------------

    def xy(self, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Local metres east/north of the region centre (fine for mock purposes)."""
        return (np.asarray(lon) - self._lon0) * self._kx, (np.asarray(lat) - self._lat0) * self._ky

    def density(self, lat: np.ndarray, lon: np.ndarray, kind: str) -> np.ndarray:
        x, y = self.xy(lat, lon)
        d2 = (x[:, None] - self._cx) ** 2 + (y[:, None] - self._cy) ** 2
        scale = 0.8 if kind == "apartments" else 1.0
        bumps = self._weights[kind] * np.exp(-d2 / (2 * (scale * self._radius) ** 2))
        background = {"residents": 0.12, "jobs": 0.01, "apartments": 0.0}[kind]
        return background + bumps.sum(axis=1)

    def nearest_centre(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        x, y = self.xy(lat, lon)
        return np.argmin((x[:, None] - self._cx) ** 2 + (y[:, None] - self._cy) ** 2, axis=1)

    def sample(self, n: int, rng: np.random.Generator, job_mix: float = 0.0
               ) -> tuple[np.ndarray, np.ndarray]:
        """n points distributed like residents (job_mix=0) or jobs (job_mix=1), or a blend."""
        lon_min, lat_min, lon_max, lat_max = self.bbox
        out_lat, out_lon = [], []
        got = 0
        while got < n:
            lat = rng.uniform(lat_min, lat_max, 4 * n + 100)
            lon = rng.uniform(lon_min, lon_max, 4 * n + 100)
            w = self._blend(lat, lon, job_mix)
            keep = rng.uniform(0, 1, w.size) < w / max(w.max(), 1.0)
            out_lat.append(lat[keep])
            out_lon.append(lon[keep])
            got += keep.sum()
        return np.concatenate(out_lat)[:n], np.concatenate(out_lon)[:n]

    def _blend(self, lat: np.ndarray, lon: np.ndarray, job_mix: float) -> np.ndarray:
        res = self.density(lat, lon, "residents") / self._peak["residents"]
        jobs = self.density(lat, lon, "jobs") / self._peak["jobs"]
        return (1 - job_mix) * res + job_mix * jobs

    # --- venue histories ----------------------------------------------------------------

    def venue_history(self, kind: VenueKind, rng: np.random.Generator, end: dt.date
                      ) -> pd.DataFrame:
        """Simulate venues opening and closing month by month.

        Each venue gets a latent `performance` (better location + less competition +
        luck). Poor performers close sooner. The places mock turns performance into
        review counts and ratings, so a mock backtest has a signal to recover.
        """
        months = pd.date_range(HISTORY_START, end, freq="MS")
        ref_lat, ref_lon = self.sample(2000, rng, kind.job_mix)
        ref = float(np.log(self._blend(ref_lat, ref_lon, kind.job_mix) + 0.05).mean())
        venues: list[dict] = []
        lat, lon = self.sample(kind.initial, rng, kind.job_mix)
        for vlat, vlon in zip(lat, lon, strict=True):
            venues.append({
                "lat": vlat, "lon": vlon, "close": None,
                "open": HISTORY_START - dt.timedelta(days=int(rng.uniform(30, 3650))),
                "performance": self._performance(vlat, vlon, venues, kind, ref, rng),
            })

        for month in months[1:]:
            month_d = month.date()
            for _ in range(rng.poisson(kind.births_per_month)):
                vlat, vlon = self.sample(1, rng, kind.job_mix)
                venues.append({
                    "lat": vlat[0], "lon": vlon[0],
                    "open": month_d + dt.timedelta(days=int(rng.integers(0, 28))),
                    "close": None,
                    "performance": self._performance(vlat[0], vlon[0], venues, kind, ref, rng),
                })
            if kind.monthly_hazard:
                covid = 1.6 if dt.date(2020, 3, 1) <= month_d <= dt.date(2021, 12, 1) else 1.0
                for v in venues:
                    if v["close"] is None and v["open"] < month_d:
                        p = kind.monthly_hazard * covid * math.exp(-0.9 * v["performance"])
                        if rng.uniform() < p:
                            v["close"] = month_d + dt.timedelta(days=int(rng.integers(0, 28)))

        df = pd.DataFrame([v for v in venues if v["open"] <= end])
        df["open"] = pd.to_datetime(df["open"])
        df["close"] = pd.to_datetime(df["close"])
        df["venue_id"] = [f"{kind.key}-{i:04d}" for i in range(len(df))]
        df["name"], df["brand"] = self._names(kind, len(df), rng)
        return df

    def _performance(self, lat: float, lon: float, venues: list[dict], kind: VenueKind,
                     ref_log_demand: float, rng: np.random.Generator) -> float:
        """Latent success: demand above typical, minus rivals within 400 m, plus luck."""
        demand = float(self._blend(np.array([lat]), np.array([lon]), kind.job_mix)[0])
        x, y = self.xy(np.array([lat]), np.array([lon]))
        open_now = [v for v in venues if v["close"] is None]
        rivals = 0
        if open_now:
            vx, vy = self.xy(np.array([v["lat"] for v in open_now]),
                             np.array([v["lon"] for v in open_now]))
            rivals = int((np.hypot(vx - x, vy - y) < 400).sum())
        demand_term = 0.9 * (math.log(demand + 0.05) - ref_log_demand)
        return demand_term - 0.10 * rivals + 0.3 + rng.normal(0, 0.7)

    @staticmethod
    def _names(kind: VenueKind, n: int, rng: np.random.Generator) -> tuple[list, list]:
        names, brands = [], []
        for i in range(n):
            if kind.brands and rng.uniform() < kind.chain_share:
                brand = str(rng.choice(kind.brands))
                names.append(brand)
                brands.append(brand)
            elif kind.key in ("cafe", "bakery", "coffee_kiosk"):
                names.append(f"{rng.choice(_CAFE_WORDS)} {rng.choice(_CAFE_SUFFIX)}")
                brands.append(None)
            else:
                base = kind.names[0] if kind.names else kind.key.title()
                names.append(f"{base} {i + 1}")
                brands.append(None)
        return names, brands
