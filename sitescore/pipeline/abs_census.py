"""ABS Census 2021 General Community Profile -> `areas` (one row per SA1)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.mock_world import mock_world

AGE_BANDS = ("age_0_4_share", "age_5_14_share", "age_15_24_share", "age_25_34_share",
             "age_35_44_share", "age_45_64_share", "age_65_plus_share")


class AbsCensus(Adapter):
    source_id = "abs_census_gcp"
    tables = ("areas",)

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        city = mock_world(ctx).city
        rng = np.random.default_rng(ctx.seed("areas"))
        n = 650
        lat, lon = city.sample(n, rng, job_mix=0.0)
        apt = np.clip(city.density(lat, lon, "apartments") + rng.normal(0, 0.08, n), 0, 0.97)

        # Age mix: apartment areas skew towards young adults, houses towards families.
        base = np.array([0.07, 0.12, 0.12, 0.19, 0.16, 0.21, 0.13])
        tilt = np.array([0.0, -0.5, 0.2, 0.8, 0.2, -0.4, -0.3])
        alpha = 80 * base[None, :] * np.exp(tilt[None, :] * (apt[:, None] - 0.4))
        ages = np.vstack([rng.dirichlet(a) for a in alpha])

        income_p = np.clip(rng.normal(780 + 420 * apt, 110), 350, 2200)
        density = city.density(lat, lon, "residents")
        lon_min, lat_min, lon_max, lat_max = ctx.region.bbox
        bbox_km2 = (lon_max - lon_min) * 92.6 * (lat_max - lat_min) * 110.5

        df = pd.DataFrame({
            "sa1_code": [f"MOCK-SA1-{i:04d}" for i in range(n)],
            "sa2_code": [f"MOCK-SA2-{c:02d}" for c in city.nearest_centre(lat, lon)],
            "lon": lon,
            "lat": lat,
            "area_sqkm": bbox_km2 / n * density.mean() / density,
            "pop_total": np.clip(rng.normal(400, 90, n), 150, 900).round(),
            **{band: ages[:, i] for i, band in enumerate(AGE_BANDS)},
            "median_income_personal_weekly": income_p.round(),
            "median_income_household_weekly":
                np.clip(income_p * rng.normal(2.3 - 0.5 * apt, 0.15), 700, 5000).round(),
            "hh_family_with_children_share": np.clip(0.48 - 0.30 * apt + rng.normal(0, 0.05, n), 0.03, 0.8),
            "hh_lone_or_group_share": np.clip(0.17 + 0.22 * apt + rng.normal(0, 0.04, n), 0.03, 0.7),
            "dwelling_apartment_share": apt,
            "tenure_renter_share": np.clip(0.25 + 0.45 * apt + rng.normal(0, 0.06, n), 0.05, 0.9),
        })
        src = ctx.source(self.source_id)
        return {"areas": stamp(df, published_at=src.published_at.date,
                               valid_from=src.valid_from, version=src.valid_from)}
