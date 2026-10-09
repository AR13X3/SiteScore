"""ABS Census 2021 Working Population Profile -> `workers` (points with worker counts).

Place-of-work counts are published down to SA2. Within each SA2 we spread the
workers over its mesh blocks in proportion to area x a job-density weight for the
block's land use (config: sources.yaml, abs_census_wpp.mesh_block_job_density),
then keep the blocks inside the study area.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sitescore.pipeline import abs_geo
from sitescore.pipeline.abs_census import read_table
from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.http import download
from sitescore.pipeline.mock_world import mock_world


def spread_workers(mb: pd.DataFrame, sa2_workers: pd.Series, density: dict[str, float]
                   ) -> pd.Series:
    """Workers per mesh block. mb needs sa2_code, category, area_sqkm."""
    weight = mb["area_sqkm"].clip(lower=0) * mb["category"].map(density).fillna(0.0)
    total = weight.groupby(mb["sa2_code"]).transform("sum")
    # SA2s with no weighted blocks at all: fall back to plain area.
    area_total = mb["area_sqkm"].groupby(mb["sa2_code"]).transform("sum")
    share = np.where(total > 0, weight / total.where(total > 0, 1), mb["area_sqkm"] / area_total)
    return pd.Series(share, index=mb.index) * mb["sa2_code"].map(sa2_workers).fillna(0.0)


class AbsWorkers(Adapter):
    source_id = "abs_census_wpp"
    tables = ("workers",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        src = ctx.source(self.source_id)
        url = src.model_extra["url"]
        zip_path = download(url, ctx.raw_dir / self.source_id / url.rsplit("/", 1)[1])
        w01b = read_table(zip_path, "W01B", geo="POW_SA2")
        sa2_workers = w01b.set_index(w01b["POW_SA2_CODE_2021"].astype(str))["P_Tot_Tot"]

        sa2_codes = sorted(abs_geo.sa1s(ctx)["sa2_code"].unique())
        mb = abs_geo.mesh_blocks_of_sa2s(ctx, sa2_codes)
        mb["workers"] = spread_workers(mb, sa2_workers, src.model_extra["mesh_block_job_density"])
        mb = mb[abs_geo.in_study_area(ctx, mb).to_numpy() & (mb["workers"] >= 0.5)]
        lon, lat = abs_geo.centroids(mb)
        df = pd.DataFrame({"point_id": mb["mb_code"].to_numpy(), "sa2_code": mb["sa2_code"].to_numpy(),
                           "lon": lon, "lat": lat, "workers": mb["workers"].round(1).to_numpy()})
        return {"workers": stamp(df, published_at=src.published_at.date,
                                 valid_from=src.valid_from, version=src.valid_from)}

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        city = mock_world(ctx).city
        rng = np.random.default_rng(ctx.seed("workers"))
        n, total = 500, 160_000
        lat, lon = city.sample(n, rng, job_mix=1.0)
        weight = rng.lognormal(0, 0.9, n) * city.density(lat, lon, "jobs")
        df = pd.DataFrame({
            "point_id": [f"MOCK-WP-{i:04d}" for i in range(n)],
            "sa2_code": [f"MOCK-SA2-{c:02d}" for c in city.nearest_centre(lat, lon)],
            "lon": lon,
            "lat": lat,
            "workers": (weight / weight.sum() * total).round(),
        })
        src = ctx.source(self.source_id)
        return {"workers": stamp(df, published_at=src.published_at.date,
                                 valid_from=src.valid_from, version=src.valid_from)}
