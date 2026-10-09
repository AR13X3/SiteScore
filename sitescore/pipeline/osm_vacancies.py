"""Vacant shopfronts from OpenStreetMap -> `vacancies` (candidate sites, never a model input).

Mappers tag empty shops `shop=vacant`, or prefix the old use (`disused:shop=*`,
`disused:amenity=cafe`, `vacant:shop=*`), often after seeing a "for lease" sign.
Coverage depends on local mappers, so these are leads to check, not listings.

Only today's map is fetched (published_at = the fetch date): a run "as of" an
earlier date sees no vacancies rather than ones it couldn't have known about.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import cached_json
from sitescore.pipeline.mock_world import mock_world
from sitescore.pipeline.osm import _padded_bbox, _run, _within_study_area

log = logging.getLogger(__name__)

# Former uses that leave a shopfront behind (not car parks, schools, toilets...).
SHOPFRONT_AMENITIES = {
    "cafe": "café", "restaurant": "restaurant", "fast_food": "takeaway", "bar": "bar",
    "pub": "pub", "bank": "bank", "pharmacy": "pharmacy", "ice_cream": "ice-cream shop",
    "post_office": "post office", "doctors": "medical practice", "dentist": "dental practice",
    "clinic": "clinic", "internet_cafe": "internet café", "money_transfer": "money transfer",
    "bureau_de_change": "currency exchange", "food_court": "food court",
}
COLUMNS = ["osm_id", "name", "lon", "lat", "kind", "former_use", "tags"]


def vacancy(tags: dict) -> tuple[str, str] | None:
    """(kind, former use) for an empty shopfront, else None. 'Former café', 'cafe'."""
    if tags.get("shop") == "vacant":
        return "Vacant shop", ""
    for key in ("disused:amenity", "was:amenity"):
        value = tags.get(key)
        if value in SHOPFRONT_AMENITIES and not tags.get("amenity"):
            return f"Former {SHOPFRONT_AMENITIES[value]}", value
    for key in ("vacant:shop", "disused:shop"):
        value = tags.get(key)
        if value and not tags.get("shop"):
            if value == "yes":
                return "Vacant shop", ""
            return f"Former shop ({value.replace('_', ' ')})", value
    return None


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    lon0, lat0, lon1, lat1 = bbox
    area = f"({lat0},{lon0},{lat1},{lon1})"
    filters = ['["shop"="vacant"]', '["disused:shop"]', '["vacant:shop"]', '["disused:amenity"]']
    return "[out:json][timeout:120];(" + "".join(f"nwr{f}{area};" for f in filters) + ");out center tags;"


def elements_to_frame(data: dict) -> pd.DataFrame:
    rows = []
    for e in data.get("elements", []):
        c = e.get("center") or e
        tags = e.get("tags", {})
        found = vacancy(tags)
        if "lat" not in c or found is None:
            continue
        rows.append({"osm_id": f"{e['type']}/{e['id']}", "name": tags.get("name", ""),
                     "lon": c["lon"], "lat": c["lat"], "kind": found[0], "former_use": found[1],
                     "tags": json.dumps(tags, ensure_ascii=False)})
    return pd.DataFrame(rows, columns=COLUMNS)


class OsmVacancies(Adapter):
    source_id = "osm_vacancies"
    tables = ("vacancies",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        osm = ctx.source("osm").model_extra
        path = ctx.raw_dir / self.source_id / f"{ctx.region.id}_{ctx.today.isoformat()}.json"
        query = overpass_query(_padded_bbox(ctx))
        data = cached_json(path, lambda: _run(list(osm["endpoints"]), query, ctx.today, ctx.today,
                                              int(osm.get("max_live_lag_days", 2))))
        df = elements_to_frame(data)
        if not df.empty:
            df = _within_study_area(ctx, df)
        log.info("OSM vacancies: %d empty shopfronts", len(df))
        today = pd.Timestamp(ctx.today)
        return {"vacancies": stamp(df, published_at=today, valid_from=today, version=today)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        """Mock cafés, bakeries and coffee kiosks that closed in the last two years."""
        today = pd.Timestamp(ctx.today)
        rows = []
        for kind, venues in mock_world(ctx).venues.values():
            if kind.key not in ("cafe", "bakery", "coffee_kiosk"):
                continue
            gone = venues[venues["close"].notna()
                          & (venues["close"] >= today - pd.DateOffset(months=24))]
            former = {"cafe": "cafe", "bakery": "bakery", "coffee_kiosk": "fast_food"}[kind.key]
            label = {"cafe": "Former café", "bakery": "Former shop (bakery)",
                     "coffee_kiosk": "Former takeaway"}[kind.key]
            for v in gone.itertuples():
                rows.append({"osm_id": f"mock:vacant-{v.venue_id}", "name": "", "lon": v.lon,
                             "lat": v.lat, "kind": label, "former_use": former,
                             "tags": json.dumps({f"disused:{'amenity' if former != 'bakery' else 'shop'}": former})})
        df = pd.DataFrame(rows, columns=COLUMNS)
        rng = np.random.default_rng(ctx.seed("vacancies"))
        df = df.sample(frac=1.0, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)
        return {"vacancies": stamp(df, published_at=today, valid_from=today, version=today)}
