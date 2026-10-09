"""ABS ASGS 2021 boundaries via the ABS ArcGIS REST service (geo.abs.gov.au).

Only the study area is requested (LGA bounding box plus buffer), so there are no
national boundary files to download. Responses are cached as GeoJSON.
"""

from __future__ import annotations

from functools import cache

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from sitescore.pipeline.base import PipelineContext
from sitescore.pipeline.http import cached_json, request

SERVICE = "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/{layer}/MapServer/0/query"
PAGE = 2000


def _query(layer: str, params: dict) -> dict:
    """GeoJSON FeatureCollection for a layer query, following pagination."""
    features, offset = [], 0
    while True:
        resp = request("GET", SERVICE.format(layer=layer), params={
            **params, "f": "geojson", "outSR": 4326,
            "resultOffset": offset, "resultRecordCount": PAGE,
        })
        page = resp.json()
        if "error" in page:
            raise RuntimeError(f"ABS {layer} query failed: {page['error']}")
        features += page.get("features", [])
        if len(page.get("features", [])) < PAGE:
            break
        offset += PAGE
    return {"type": "FeatureCollection", "features": features}


def _envelope(ctx: PipelineContext) -> str:
    """Region bbox padded by the buffer (~1 km per 0.009 degrees), as an ArcGIS envelope."""
    pad = ctx.region.buffer_m / 111_000 * 1.2
    lon0, lat0, lon1, lat1 = ctx.region.bbox
    return f"{lon0 - pad},{lat0 - pad},{lon1 + pad},{lat1 + pad}"


def _layer(ctx: PipelineContext, layer: str, fields: str, name: str) -> gpd.GeoDataFrame:
    path = ctx.raw_dir / "abs_boundaries" / f"{ctx.region.id}_{name}.geojson"
    data = cached_json(path, lambda: _query(layer, {
        "geometry": _envelope(ctx), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "where": "1=1", "outFields": fields,
        "maxAllowableOffset": 0.00002,  # ~2 m generalisation keeps responses small
    }))
    return gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")


def lga_polygon(ctx: PipelineContext) -> BaseGeometry:
    path = ctx.raw_dir / "abs_boundaries" / f"lga_{ctx.region.lga_code}.geojson"
    data = cached_json(path, lambda: _query("LGA", {
        "where": f"lga_code_2021='{ctx.region.lga_code}'", "outFields": "lga_code_2021"}))
    if not data["features"]:
        raise RuntimeError(f"LGA {ctx.region.lga_code} not found")
    return shape(data["features"][0]["geometry"])


def study_area(ctx: PipelineContext) -> BaseGeometry:
    """LGA polygon buffered by region.buffer_m, in the region's metric CRS."""
    return _study_area(ctx.region.id, ctx.region.metric_crs, ctx.region.buffer_m, lga_polygon(ctx))


@cache
def _study_area(region_id: str, crs: str, buffer_m: float, lga: BaseGeometry) -> BaseGeometry:
    return gpd.GeoSeries([lga], crs="EPSG:4326").to_crs(crs).buffer(buffer_m).iloc[0]


def sa1s(ctx: PipelineContext) -> gpd.GeoDataFrame:
    """SA1s whose centroid lies in the study area: sa1_code, sa2_code, area_sqkm, geometry."""
    gdf = _layer(ctx, "SA1", "sa1_code_2021,sa2_code_2021,area_albers_sqkm", "sa1")
    return _in_study_area(ctx, gdf).rename(columns={
        "sa1_code_2021": "sa1_code", "sa2_code_2021": "sa2_code", "area_albers_sqkm": "area_sqkm"})


def mesh_blocks(ctx: PipelineContext) -> gpd.GeoDataFrame:
    """Mesh blocks in the study area: mb_code, category, sa2_code, area_sqkm, geometry."""
    gdf = _layer(ctx, "MB", "mb_code_2021,mb_category_2021,sa2_code_2021,area_albers_sqkm", "mb")
    return _in_study_area(ctx, gdf).rename(columns={
        "mb_code_2021": "mb_code", "mb_category_2021": "category", "sa2_code_2021": "sa2_code",
        "area_albers_sqkm": "area_sqkm"})


def mesh_blocks_of_sa2s(ctx: PipelineContext, sa2_codes: list[str]) -> gpd.GeoDataFrame:
    """Every mesh block of the given SA2s, including parts outside the study area.

    Needed to spread an SA2's workers over the whole SA2, not just the part we keep.
    """
    codes = ",".join(f"'{c}'" for c in sorted(sa2_codes))
    path = ctx.raw_dir / "abs_boundaries" / f"{ctx.region.id}_mb_full_sa2.geojson"
    data = cached_json(path, lambda: _query("MB", {
        "where": f"sa2_code_2021 IN ({codes})",
        "outFields": "mb_code_2021,mb_category_2021,sa2_code_2021,area_albers_sqkm",
        "maxAllowableOffset": 0.00002,
    }))
    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    return gdf.rename(columns={
        "mb_code_2021": "mb_code", "mb_category_2021": "category", "sa2_code_2021": "sa2_code",
        "area_albers_sqkm": "area_sqkm"})


def in_study_area(ctx: PipelineContext, gdf: gpd.GeoDataFrame) -> pd.Series:
    """Boolean mask: representative point of each geometry lies in the study area."""
    return pd.Series(
        gdf.to_crs(ctx.region.metric_crs).representative_point().within(study_area(ctx)).to_numpy(),
        index=gdf.index)


def _in_study_area(ctx: PipelineContext, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf[in_study_area(ctx, gdf).to_numpy()].reset_index(drop=True)


def centroids(gdf: gpd.GeoDataFrame) -> tuple:
    """(lon, lat) arrays of points guaranteed to lie inside each polygon."""
    pts = gdf.representative_point()
    return pts.x.to_numpy(), pts.y.to_numpy()
