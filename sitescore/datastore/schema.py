"""Canonical tables: the contract between the data pipeline and the model.

Every source adapter (real or mock) must produce exactly these columns, plus
the dating columns that make "as of" runs possible:

    published_at  when the row became publicly available (the leakage cut-off)
    valid_from    start of the period the row describes (never after published_at)
    valid_to      end of that period (NaT = open-ended); descriptive only
    version       for "latest" tables: which release/snapshot the row belongs to

As of date D the model sees rows with published_at <= D, nothing else.

Two kinds of table:
    latest      a series of complete releases (Census vintages, OSM snapshots).
                As of date D you see only the newest release published by D.
    cumulative  a stream of records (monthly patronage, DA events).
                As of date D you see every record published by D.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sitescore.features import FEATURES

DATING_COLUMNS = ("published_at", "valid_from", "valid_to")


@dataclass(frozen=True)
class TableSpec:
    name: str
    source: str  # key in config/sources.yaml
    kind: Literal["latest", "cumulative"]
    columns: tuple[str, ...]
    description: str
    # False = outcome data (e.g. Google ratings today). The model may never read it;
    # only the backtest scorer can, after the prediction is made.
    model_visible: bool = True

    @property
    def required_columns(self) -> tuple[str, ...]:
        extra = ("version",) if self.kind == "latest" else ()
        return self.columns + DATING_COLUMNS + extra


TABLES: dict[str, TableSpec] = {
    t.name: t
    for t in [
        TableSpec(
            "areas", "abs_census_gcp", "latest",
            ("sa1_code", "sa2_code", "lon", "lat", "area_sqkm", *FEATURES),
            "Census small areas (SA1): centroid and demographic features",
        ),
        TableSpec(
            "workers", "abs_census_wpp", "latest",
            ("point_id", "sa2_code", "lon", "lat", "workers"),
            "Workers by place of work, placed on non-residential mesh blocks",
        ),
        TableSpec(
            "station_usage", "tfnsw_station_usage", "cumulative",
            ("station", "lon", "lat", "month", "entries", "exits"),
            "Monthly entries and exits per train/metro/light-rail station",
        ),
        TableSpec(
            "pois", "osm", "latest",
            ("osm_id", "name", "lon", "lat", "tags"),
            "Points of interest (competitors, anchors); tags is a JSON object of OSM tags",
        ),
        TableSpec(
            "developments", "planning_da", "cumulative",
            ("da_id", "lon", "lat", "new_dwellings", "event", "event_date"),
            "Development application events: lodged / approved / refused",
        ),
        TableSpec(
            "poi_history", "osm_history", "cumulative",
            ("osm_id", "seq", "name", "lon", "lat", "tags", "deleted", "changeset"),
            "Every edit of each mapped business (OSM element history). Outcome data: "
            "backtest only (when a business closed and what replaced it)",
            model_visible=False,
        ),
        TableSpec(
            "places", "google_places", "latest",
            ("place_id", "osm_id", "name", "lon", "lat", "rating", "review_count",
             "business_status"),
            "Google Places snapshot. Outcome data: backtest ground truth only",
            model_visible=False,
        ),
        TableSpec(
            "overture_places", "overture_places", "latest",
            ("overture_id", "name", "lon", "lat", "category", "operating_status", "confidence"),
            "Overture Maps places (cafes, gyms, childcare). Outcome data: backtest only",
            model_visible=False,
        ),
        TableSpec(
            "fsq_places", "foursquare_places", "latest",
            ("fsq_place_id", "name", "lon", "lat", "category", "date_created", "date_refreshed",
             "date_closed"),
            "Foursquare Open Source Places with added/closed dates. Outcome data: backtest only",
            model_visible=False,
        ),
        TableSpec(
            "business_names", "asic_business_names", "latest",
            ("bn_name", "status", "registered", "cancelled", "abn"),
            "ASIC business names matching businesses in the region. Outcome data: backtest only",
            model_visible=False,
        ),
    ]
}
