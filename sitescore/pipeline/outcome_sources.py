"""Free outcome sources for backtests: Overture Places, Foursquare OS Places, ASIC names.

None of these are model inputs (their tables are model_visible=False). They tell
the backtest whether a business is still trading:

- Overture: is it still listed, and how confident is Overture that it exists?
  (Every place in the area is kept: categories differ between sources, so
  matching is by name and location, not category.)
- Foursquare: when it was added, last refreshed, and when it was marked closed.
- ASIC: is a business name registered around its opening still registered?

Parquet sources are read with DuckDB, filtered to the region, so nothing global
is downloaded. Results are cached per release under raw_dir.
"""

from __future__ import annotations

import json
import logging
import re
import zipfile

import duckdb
import numpy as np
import pandas as pd

from sitescore.matching import normalise_name
from sitescore.pipeline import abs_geo
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import download, request
from sitescore.pipeline.mock_world import mock_world

log = logging.getLogger(__name__)

SCORED_KINDS = {"cafe": "cafe", "gym": "gym", "childcare": "child_care_and_day_care"}


def _padded_bbox(ctx: PipelineContext) -> tuple[float, float, float, float]:
    pad = ctx.region.buffer_m / 111_000 * 1.2
    lon0, lat0, lon1, lat1 = ctx.region.bbox
    return lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad


def _in_area(ctx: PipelineContext, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    pts = abs_geo.gpd.GeoDataFrame(geometry=abs_geo.gpd.points_from_xy(df["lon"], df["lat"]),
                                   crs="EPSG:4326")
    return df[abs_geo.in_study_area(ctx, pts).to_numpy()].reset_index(drop=True)


def _duckdb() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    return con


def _cached_parquet(path, build) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    df = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _mock_venues(ctx: PipelineContext) -> pd.DataFrame:
    """Every mock cafe/gym/childcare venue ever, with its kind."""
    world = mock_world(ctx)
    return pd.concat([world.venues[k][1].assign(kind=k) for k in SCORED_KINDS],
                     ignore_index=True)


# --- Overture Maps Places ----------------------------------------------------------------


class OverturePlaces(Adapter):
    source_id = "overture_places"
    tables = ("overture_places",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        extra = ctx.source(self.source_id).model_extra
        release = request("GET", extra["catalog"], timeout=30).json()["latest"]
        version = pd.Timestamp(release[:10])
        lon0, lat0, lon1, lat1 = _padded_bbox(ctx)
        path = ctx.raw_dir / self.source_id / f"{ctx.region.id}_{release}_all.parquet"

        def build() -> pd.DataFrame:
            con = _duckdb()
            con.execute("SET s3_region='us-west-2';")
            return con.execute(f"""
                SELECT id AS overture_id, names.primary AS name, basic_category AS category,
                       operating_status, confidence, ST_X(geometry) AS lon, ST_Y(geometry) AS lat
                FROM read_parquet('{extra["s3"].format(release=release)}', hive_partitioning=1)
                WHERE bbox.xmin BETWEEN {lon0} AND {lon1} AND bbox.ymin BETWEEN {lat0} AND {lat1}
                """).df()

        df = _in_area(ctx, _cached_parquet(path, build))
        log.info("Overture %s: %d places", release, len(df))
        return {"overture_places": stamp(df, published_at=version, valid_from=version,
                                         version=version)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        rng = np.random.default_rng(ctx.seed("overture"))
        today = pd.Timestamp(ctx.today)
        v = _mock_venues(ctx)
        recently_closed = v["close"].notna() & (v["close"] >= today - pd.DateOffset(months=18))
        listed = v[v["close"].isna() | recently_closed]
        conf = np.where(listed["close"].isna(),
                        np.clip(0.8 + 0.08 * listed["performance"] + rng.normal(0, 0.08, len(listed)),
                                0.4, 0.99),
                        rng.uniform(0.2, 0.55, len(listed)))  # stale listings fade
        df = pd.DataFrame({
            "overture_id": "mock-ov-" + listed["venue_id"], "name": listed["name"],
            "lon": listed["lon"], "lat": listed["lat"],
            "category": listed["kind"].map(SCORED_KINDS), "operating_status": None,
            "confidence": conf,
        })
        version = today - pd.Timedelta(days=20)
        return {"overture_places": stamp(df, published_at=version, valid_from=version,
                                         version=version)}


# --- Foursquare Open Source Places --------------------------------------------------------


class FoursquarePlaces(Adapter):
    source_id = "foursquare_places"
    tables = ("fsq_places",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        extra = ctx.source(self.source_id).model_extra
        con = _duckdb()
        files, release = None, None
        if ctx.settings.hf_token:
            try:
                files, release = self._hugging_face(con, extra, ctx.settings.hf_token)
            except Exception as exc:  # noqa: BLE001 - fall back to the public mirror
                log.warning("Foursquare via Hugging Face failed (%s); using public mirror", exc)
        if files is None:
            files, release = self._public_mirror(extra)
        lon0, lat0, lon1, lat1 = _padded_bbox(ctx)
        path = ctx.raw_dir / self.source_id / f"{ctx.region.id}_{release}_all.parquet"

        def build() -> pd.DataFrame:
            return con.execute(f"""
                SELECT fsq_place_id, name, latitude AS lat, longitude AS lon,
                       fsq_category_labels[1] AS category,
                       date_created, date_refreshed, date_closed
                FROM read_parquet(?)
                WHERE latitude BETWEEN {lat0} AND {lat1} AND longitude BETWEEN {lon0} AND {lon1}
            """, [files]).df()

        df = _in_area(ctx, _cached_parquet(path, build))
        for col in ("date_created", "date_refreshed", "date_closed"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
        version = pd.Timestamp(release)
        log.info("Foursquare %s: %d places", release, len(df))
        return {"fsq_places": stamp(df, published_at=version, valid_from=version,
                                    version=version)}

    @staticmethod
    def _public_mirror(extra: dict) -> tuple[list[str], str]:
        listing = request("GET", extra["public_listing"], timeout=60).text
        keys = re.findall(r"<Key>(fsq-os-places/(\d{4}-\d{2}-\d{2})/places/[^<]+\.parquet)</Key>",
                          listing)
        release = max(d for _, d in keys)
        base = extra["public_listing"].split("fsq-os-places/")[0]
        return [base + k for k, d in keys if d == release], release

    @staticmethod
    def _hugging_face(con: duckdb.DuckDBPyConnection, extra: dict, token: str
                      ) -> tuple[list[str], str]:
        api = f"https://huggingface.co/api/datasets/{extra['hf_dataset']}/tree/main/release"
        dirs = request("GET", api, headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
        release = max(re.search(r"dt=(\d{4}-\d{2}-\d{2})", d["path"]).group(1)
                      for d in dirs if "dt=" in d["path"])
        con.execute(f"CREATE SECRET hf (TYPE huggingface, TOKEN '{token}');")
        glob = f"hf://datasets/{extra['hf_dataset']}/release/dt={release}/places/parquet/*.parquet"
        return [glob], release

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        rng = np.random.default_rng(ctx.seed("foursquare"))
        snapshot = pd.Timestamp("2025-02-06")  # same date as the public mirror's last release
        v = _mock_venues(ctx)
        v = v[v["open"] <= snapshot]
        closed = v["close"].notna() & (v["close"] <= snapshot)
        created = v["open"] + pd.to_timedelta(rng.uniform(0, 120, len(v)), unit="D")
        end = v["close"].where(closed, snapshot)
        refreshed = end - pd.to_timedelta(rng.uniform(0, 200, len(v)), unit="D")
        df = pd.DataFrame({
            "fsq_place_id": "mock-fsq-" + v["venue_id"], "name": v["name"],
            "lon": v["lon"], "lat": v["lat"], "category": v["kind"].str.title(),
            "date_created": created.clip(upper=snapshot), "date_refreshed": refreshed.clip(lower=created),
            "date_closed": v["close"].where(closed),
        })
        return {"fsq_places": stamp(df, published_at=snapshot, valid_from=snapshot,
                                    version=snapshot)}


# --- ASIC business names -----------------------------------------------------------------


class AsicBusinessNames(Adapter):
    source_id = "asic_business_names"
    tables = ("business_names",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        if ctx.store is None:
            raise RuntimeError("needs the store (names of businesses in the region)")
        wanted = names_in_region(ctx)
        if not wanted:
            raise RuntimeError("no business names in the region to look up yet")
        extra = ctx.source(self.source_id).model_extra
        resources = request("GET", extra["package_api"], timeout=60).json()["result"]["resources"]
        url = next(r["url"] for r in resources if (r.get("format") or "").upper() == "ZIP")
        zip_path = download(url, ctx.raw_dir / self.source_id / url.rsplit("/", 1)[1])
        df = read_business_names(zip_path, wanted)
        today = pd.Timestamp(ctx.today)
        log.info("ASIC: %d business names match businesses in the region", len(df))
        return {"business_names": stamp(df, published_at=today, valid_from=today, version=today)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        rng = np.random.default_rng(ctx.seed("asic"))
        today = pd.Timestamp(ctx.today)
        v = _mock_venues(ctx)
        v = v[v["brand"].isna() & (v["open"] >= pd.Timestamp("2016-01-01"))]
        # The extract keeps deregistered names for 12 months only.
        v = v[v["close"].isna() | (v["close"] >= today - pd.DateOffset(months=12))]
        registered = v["open"] - pd.to_timedelta(rng.uniform(10, 200, len(v)), unit="D")
        cancelled = (v["close"] + pd.to_timedelta(rng.uniform(0, 60, len(v)), unit="D"))
        df = pd.DataFrame({
            "bn_name": v["name"].str.upper(),
            "status": np.where(v["close"].isna(), "Registered", "Deregistered"),
            "registered": registered,
            "cancelled": cancelled.where(v["close"].notna()).clip(upper=today),
            "abn": [f"{rng.integers(10**10, 10**11)}" for _ in range(len(v))],
        })
        return {"business_names": stamp(df, published_at=today, valid_from=today, version=today)}


def names_in_region(ctx: PipelineContext) -> set[str]:
    """Normalised names of scored businesses from every map source in the store."""
    store, names = ctx.store, set()
    if store.has("pois"):
        pois = store.read("pois")
        kinds = pois["tags"].map(lambda t: _kind(json.loads(t)))
        names |= set(pois.loc[kinds.notna(), "name"].dropna())
    for table in ("overture_places", "fsq_places"):
        if store.has(table) and store.provenance(table) == store.provenance("pois"):
            names |= set(store.read(table)["name"].dropna())
    return {normalise_name(n) for n in names if normalise_name(n)}


def _kind(tags: dict) -> str | None:
    if tags.get("amenity") in ("cafe", "childcare") or tags.get("leisure") == "fitness_centre":
        return "scored"
    return None


def read_business_names(zip_path, wanted: set[str]) -> pd.DataFrame:
    """Rows of the (tab-separated) register whose normalised name is in `wanted`."""
    cols = {"BN_NAME": "bn_name", "BN_STATUS": "status", "BN_REG_DT": "registered",
            "BN_CANCEL_DT": "cancelled", "BN_ABN": "abn"}
    keep = []
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith((".csv", ".txt")))
        for chunk in pd.read_csv(z.open(name), sep="\t", dtype=str, usecols=list(cols),
                                 chunksize=500_000, encoding="latin-1"):
            hit = chunk["BN_NAME"].fillna("").map(normalise_name).isin(wanted)
            keep.append(chunk[hit])
    df = pd.concat(keep, ignore_index=True).rename(columns=cols)
    for col in ("registered", "cancelled"):
        df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")
    return df

