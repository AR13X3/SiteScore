"""Address search: NSW Spatial Services address points, fallback OSM Nominatim.

Used live by the API when someone types an address. Results are limited to the
region's bounding box (plus buffer).
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from sitescore.config import Region, load_region, load_sources
from sitescore.pipeline.http import FetchError, request

log = logging.getLogger(__name__)

ABBREVIATIONS = {
    "ST": "STREET", "RD": "ROAD", "AVE": "AVENUE", "AV": "AVENUE", "PDE": "PARADE",
    "HWY": "HIGHWAY", "DR": "DRIVE", "PL": "PLACE", "CRES": "CRESCENT", "CR": "CRESCENT",
    "LN": "LANE", "CT": "COURT", "TCE": "TERRACE", "BVD": "BOULEVARD", "BLVD": "BOULEVARD",
    "CL": "CLOSE", "SQ": "SQUARE", "WY": "WAY", "GR": "GROVE", "CCT": "CIRCUIT",
}
STATES = {"NSW", "NEW", "SOUTH", "WALES", "AUSTRALIA"}


def normalise_address(q: str) -> str:
    """'20 George St, Parramatta NSW 2150' -> '20 GEORGE STREET PARRAMATTA'.

    The result contains only A-Z, 0-9, space, '/' and '-', so it is safe to put
    inside the address service's query.
    """
    words = re.sub(r"[^A-Z0-9/\- ]", " ", q.upper()).split()
    out = []
    for w in words:
        if w in STATES or re.fullmatch(r"2\d{3}", w):  # state names, NSW postcodes
            continue
        out.append(ABBREVIATIONS.get(w, w))
    return " ".join(out)


def _envelope(region: Region) -> str:
    pad = region.buffer_m / 111_000 * 1.2
    lon0, lat0, lon1, lat1 = region.bbox
    return f"{lon0 - pad},{lat0 - pad},{lon1 + pad},{lat1 + pad}"


def _nsw(address: str, region: Region, url: str, limit: int) -> list[dict]:
    results: list[dict] = []
    for pattern in (f"{address}%", f"%{address}%"):
        resp = request("GET", url, retries=1, backoff=1, timeout=20, params={
            "where": f"address LIKE '{pattern}'", "outFields": "address", "outSR": 4326,
            "geometry": _envelope(region), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "resultRecordCount": limit, "f": "json",
        })
        body = resp.json()
        if "error" in body:
            raise FetchError(str(body["error"]))
        results = [{"label": f["attributes"]["address"].title(), "lat": f["geometry"]["y"],
                    "lon": f["geometry"]["x"], "source": "NSW Spatial Services"}
                   for f in body.get("features", [])]
        if results:
            break
    return results


def _nominatim(q: str, region: Region, url: str, limit: int) -> list[dict]:
    lon0, lat0, lon1, lat1 = region.bbox
    resp = request("GET", url, retries=1, backoff=1, timeout=20, params={
        "q": q, "format": "json", "limit": limit, "countrycodes": region.geocoding["country_code"],
        "viewbox": f"{lon0},{lat1},{lon1},{lat0}", "bounded": 1,
    })
    return [{"label": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"]),
             "source": "OpenStreetMap Nominatim"} for r in resp.json()]


@lru_cache(maxsize=512)
def search(q: str, limit: int = 5) -> tuple[dict, ...]:
    """Up to `limit` matches for a free-text address, best first."""
    address = normalise_address(q)
    if len(address) < 3:
        return ()
    region, src = load_region(), load_sources()["geocoding"]
    url = src.model_extra["url"].rstrip("/") + "/1/query"
    try:
        found = _nsw(address, region, url, limit)
        if found:
            return tuple(found)
    except FetchError as exc:
        log.warning("NSW address search failed, trying Nominatim: %s", exc)
    try:
        return tuple(_nominatim(q, region, src.model_extra["fallback_url"], limit))
    except FetchError as exc:
        log.warning("Nominatim failed: %s", exc)
        return ()
