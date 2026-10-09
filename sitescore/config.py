"""Load and validate the YAML configuration in config/.

Every model is strict (unknown keys are errors) so a typo in a YAML file fails
loudly at startup instead of silently using a default.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sitescore.features import FEATURES
from sitescore.paths import CONFIG_DIR
from sitescore.settings import get_settings

SegmentName = Literal["residents", "workers", "commuters"]
SEGMENTS: tuple[SegmentName, ...] = ("residents", "workers", "commuters")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_feature(name: str) -> str:
    if name not in FEATURES:
        raise ValueError(f"unknown feature {name!r}; available: {sorted(FEATURES)}")
    return name


def _all_segments(d: dict) -> dict:
    missing = set(SEGMENTS) - set(d)
    if missing:
        raise ValueError(f"missing segments: {sorted(missing)}")
    return d


# --- Business profiles -----------------------------------------------------------


class TagRule(Strict):
    """OSM tag filter, e.g. {amenity: cafe}. A value of "*" matches any value."""

    tags: dict[str, str]
    weight: float = Field(1.0, ge=0)


class Anchors(Strict):
    radius_m: float = Field(gt=0)
    items: list[TagRule]
    max_boost: float = Field(ge=0)


class Segment(Strict):
    participation: float = Field(ge=0, le=1)
    visits_per_month: float = Field(ge=0)
    max_walk_minutes: float = Field(gt=0)
    fit_applies: bool = False
    population_scale: str | None = None

    @field_validator("population_scale")
    @classmethod
    def _feature(cls, v: str | None) -> str | None:
        return None if v is None else _check_feature(v)


class Daypart(Strict):
    name: str
    hours: tuple[int, int]
    trade_share: float = Field(ge=0, le=1)
    presence: dict[SegmentName, float]

    @field_validator("presence")
    @classmethod
    def _complete(cls, v: dict) -> dict:
        return _all_segments(v)


class FitFeature(Strict):
    weight: float
    why: str = ""


class Fit(Strict):
    strength: float = Field(ge=0)
    clip: tuple[float, float]
    features: dict[str, FitFeature]

    @field_validator("features")
    @classmethod
    def _known(cls, v: dict) -> dict:
        for name in v:
            _check_feature(name)
        return v


class OurStore(Strict):
    attractiveness: float = Field(gt=0)
    quality: float = 0.0


class Pricing(Strict):
    reference_price: float = Field(gt=0)
    our_price: float = Field(gt=0)
    price_range: tuple[float, float]
    unit_cost: float = Field(ge=0)

    @model_validator(mode="after")
    def _in_range(self) -> Pricing:
        lo, hi = self.price_range
        if not (lo < hi and lo <= self.our_price <= hi and lo <= self.reference_price <= hi):
            raise ValueError("price_range must contain our_price and reference_price")
        if self.unit_cost >= lo:
            raise ValueError("unit_cost must be below the lowest allowed price")
        return self


class Spend(Strict):
    avg_transaction_value: float = Field(gt=0)
    atv_price_elasticity: float = 1.0
    capacity_visits_per_month: float | None = Field(None, gt=0)


class Costs(Strict):
    rent_per_month: float = Field(ge=0)
    wages_per_month: float = Field(ge=0)
    cogs_share: float = Field(ge=0, le=1)
    other_fixed_per_month: float = Field(0, ge=0)


class Dynamics(Strict):
    ramp_start_share: float = Field(gt=0, le=1)
    ramp_months_to_90pct: float = Field(gt=0)
    seasonality: Annotated[list[float], Field(min_length=12, max_length=12)]
    school_holiday_effect: dict[SegmentName, float]


class BusinessProfile(Strict):
    id: str
    name: str
    description: str
    status: Literal["ready", "draft"]
    competitors: Annotated[list[TagRule], Field(min_length=1)]
    anchors: Anchors
    segments: dict[SegmentName, Segment]
    dayparts: Annotated[list[Daypart], Field(min_length=1)]
    weekend_trade_share: float = Field(ge=0, le=1)
    weekend_presence: dict[SegmentName, float]
    fit: Fit
    our_store: OurStore
    pricing: Pricing
    spend: Spend
    costs: Costs | None = None
    dynamics: Dynamics

    @field_validator("segments", "weekend_presence")
    @classmethod
    def _complete(cls, v: dict) -> dict:
        return _all_segments(v)

    @field_validator("dayparts")
    @classmethod
    def _shares_sum_to_one(cls, v: list[Daypart]) -> list[Daypart]:
        total = sum(d.trade_share for d in v)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"daypart trade_share must sum to 1 (got {total:.2f})")
        return v


# --- Global model config --------------------------------------------------------------


class NormalRel(Strict):
    dist: Literal["normal_rel"]
    sd: float = Field(gt=0)


class Uniform(Strict):
    dist: Literal["uniform"]
    low: float
    high: float


class Triangular(Strict):
    dist: Literal["triangular"]
    low: float
    mode: float
    high: float


Distribution = Annotated[NormalRel | Uniform | Triangular, Field(discriminator="dist")]


class DistanceCfg(Strict):
    detour_factor: float = Field(ge=1)
    walk_speed_kmh: float = Field(gt=0)
    min_distance_m: float = Field(gt=0)


class OutsideOption(Strict):
    attractiveness: float = Field(ge=0)
    distance_m: float = Field(gt=0)


class HuffCfg(Strict):
    alpha: float = Field(gt=0)
    beta: float = Field(gt=0)
    outside_option: OutsideOption


class CompetitorAttractiveness(Strict):
    default: float = Field(gt=0)
    chain: float = Field(gt=0)
    kiosk: float = Field(gt=0)


class Utility(Strict):
    distance_per_km: float
    price_per_dollar: float
    quality: float
    habit: float


class Awareness(Strict):
    start: float = Field(ge=0, le=1)
    months_to_full: int = Field(ge=1)


class AbmCfg(Strict):
    n_agents: int = Field(ge=100)
    months: int = Field(ge=1)
    seed: int
    utility: Utility
    heterogeneity_sigma: float = Field(ge=0)
    habit_decay: float = Field(ge=0, le=1)
    awareness: Awareness


class GameCfg(Strict):
    enabled: bool
    radius_m: float = Field(gt=0)
    max_rounds: int = Field(ge=1)
    tolerance: float = Field(gt=0)
    price_step: float = Field(gt=0)
    response_speed: float = Field(gt=0, le=1)


class MonteCarloCfg(Strict):
    n_runs: int = Field(ge=1)
    seed: int
    percentiles: list[int]
    parameters: dict[str, Distribution]


class BuildTime(Strict):
    max_dwellings: int
    months: int


class DevelopmentsCfg(Strict):
    persons_per_new_dwelling: float = Field(gt=0)
    build_months: list[BuildTime]
    occupancy_ramp_months: int = Field(ge=0)


class ModelConfig(Strict):
    horizon_months: int = Field(ge=1, le=120)
    distance: DistanceCfg
    huff: HuffCfg
    competitor_attractiveness: CompetitorAttractiveness
    abm: AbmCfg
    game: GameCfg
    montecarlo: MonteCarloCfg
    developments: DevelopmentsCfg


# --- Region, calendar, sources --------------------------------------------------------


class MapCfg(Strict):
    center: tuple[float, float]
    zoom: int


class Region(Strict):
    id: str
    name: str
    state: str
    asgs_edition: int
    lga_code: str
    bbox: tuple[float, float, float, float]
    buffer_m: float = Field(ge=0)
    metric_crs: str
    map: MapCfg
    census: dict[str, Any]
    planning_portal: dict[str, list[str]]
    geocoding: dict[str, str]

    @field_validator("bbox")
    @classmethod
    def _ordered(cls, v: tuple) -> tuple:
        lon0, lat0, lon1, lat1 = v
        if not (lon0 < lon1 and lat0 < lat1):
            raise ValueError("bbox must be [lon_min, lat_min, lon_max, lat_max]")
        return v


class Calendar(Strict):
    school_holiday_fraction: dict[int, float]

    @field_validator("school_holiday_fraction")
    @classmethod
    def _months(cls, v: dict[int, float]) -> dict[int, float]:
        if sorted(v) != list(range(1, 13)) or not all(0 <= x <= 1 for x in v.values()):
            raise ValueError("need a fraction in [0, 1] for each month 1..12")
        return v


class PublishedAt(Strict):
    rule: Literal["fixed", "per_record", "snapshot", "fetched"]
    date: dt.date | None = None
    lag_days: int | None = None

    @model_validator(mode="after")
    def _fixed_has_date(self) -> PublishedAt:
        if self.rule == "fixed" and self.date is None:
            raise ValueError("fixed rule needs a date")
        return self


class Source(BaseModel):
    """Descriptive fields (urls, licence...) are free-form; dating rules are not."""

    model_config = ConfigDict(extra="allow", frozen=True)
    title: str
    provider: str
    licence: str
    published_at: PublishedAt
    valid_from: dt.date | None = None
    used_for: str
    needs_key: bool = False
    env_key: str | None = None


# --- Loaders ----------------------------------------------------------------------------


def _read(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_model_config() -> ModelConfig:
    cfg = ModelConfig.model_validate(_read(CONFIG_DIR / "model.yaml"))
    for path in cfg.montecarlo.parameters:
        if path.startswith("model.") and not expand_path(cfg.model_dump(), path.removeprefix("model.")):
            raise ValueError(f"montecarlo parameter {path!r} matches nothing in model.yaml")
    return cfg


@lru_cache
def load_business_types() -> dict[str, BusinessProfile]:
    profiles = {}
    for path in sorted((CONFIG_DIR / "business_types").glob("*.yaml")):
        try:
            profile = BusinessProfile.model_validate(_read(path))
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if profile.id != path.stem:
            raise ValueError(f"{path.name}: id {profile.id!r} must match the file name")
        profiles[profile.id] = profile
    return profiles


def load_business_type(type_id: str) -> BusinessProfile:
    try:
        return load_business_types()[type_id]
    except KeyError:
        raise KeyError(f"unknown business type {type_id!r}") from None


@lru_cache
def load_region(region_id: str | None = None) -> Region:
    region_id = region_id or get_settings().region
    path = CONFIG_DIR / "regions" / f"{region_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no region config at {path}")
    return Region.model_validate(_read(path))


@lru_cache
def load_calendar(state: str) -> Calendar:
    return Calendar.model_validate(_read(CONFIG_DIR / "calendars" / f"{state.lower()}.yaml"))


@lru_cache
def load_sources() -> dict[str, Source]:
    return {k: Source.model_validate(v) for k, v in _read(CONFIG_DIR / "sources.yaml").items()}


# --- Dotted-path helpers (used by Monte Carlo to vary config values) ---------------------


def expand_path(data: dict, pattern: str) -> list[str]:
    """Concrete dotted paths in `data` matching `pattern` (segments may be globs, e.g. *)."""
    paths = [""]
    for part in pattern.split("."):
        nxt = []
        for prefix in paths:
            node = get_path(data, prefix) if prefix else data
            if isinstance(node, dict):
                nxt += [f"{prefix}.{k}" if prefix else k for k in node if fnmatch.fnmatch(str(k), part)]
        paths = nxt
    return [p for p in paths if _is_number(get_path(data, p))]


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def get_path(data: dict, path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        node = node[part]
    return node
