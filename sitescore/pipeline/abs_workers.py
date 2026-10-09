"""ABS Census 2021 Working Population Profile -> `workers` (points with worker counts)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.mock_world import mock_world


class AbsWorkers(Adapter):
    source_id = "abs_census_wpp"
    tables = ("workers",)

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
