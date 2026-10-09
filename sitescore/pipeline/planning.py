"""NSW Planning Portal online DA data -> `developments` (one row per DA event).

A DA is stored as events (lodged, then approved or refused), each published on
the day it happened. As of any date the model therefore sees only what was
known then: a DA approved in 2024 is just "lodged" in a 2023 run.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.mock_world import mock_world

MOCK_FIRST_LODGED = dt.date(2019, 1, 1)


class PlanningDA(Adapter):
    source_id = "planning_da"
    tables = ("developments",)

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        city = mock_world(ctx).city
        rng = np.random.default_rng(ctx.seed("developments"))
        n = 420
        size = rng.choice(["small", "medium", "large", "tower"], n, p=[0.70, 0.20, 0.08, 0.02])
        dwellings = np.select(
            [size == "small", size == "medium", size == "large"],
            [rng.integers(1, 3, n), rng.integers(3, 31, n), rng.integers(31, 201, n)],
            rng.integers(201, 601, n),
        )
        # Bigger projects go where apartments already cluster.
        lat, lon = city.sample(n, rng, job_mix=0.0)
        big = dwellings > 30
        apt_lat, apt_lon = self._near_apartments(city, int(big.sum()), rng)
        lat[big], lon[big] = apt_lat, apt_lon

        span = (ctx.today - MOCK_FIRST_LODGED).days
        lodged = [MOCK_FIRST_LODGED + dt.timedelta(days=int(d)) for d in rng.uniform(0, span, n)]
        months_to_decide = 3 + 0.06 * dwellings ** 0.8 + rng.exponential(2.5, n)
        outcome = rng.choice(["approved", "refused"], n, p=[0.88, 0.12])

        rows = []
        for i in range(n):
            base = {"da_id": f"MOCK-PAN-{i:05d}", "lon": lon[i], "lat": lat[i],
                    "new_dwellings": int(dwellings[i])}
            rows.append({**base, "event": "lodged", "event_date": lodged[i]})
            decided = lodged[i] + dt.timedelta(days=int(months_to_decide[i] * 30.4))
            if decided <= ctx.today:
                rows.append({**base, "event": outcome[i], "event_date": decided})
        df = pd.DataFrame(rows)
        df["event_date"] = pd.to_datetime(df["event_date"])
        return {"developments": stamp(df, published_at=df["event_date"],
                                      valid_from=df["event_date"])}

    @staticmethod
    def _near_apartments(city, n: int, rng: np.random.Generator):
        lat, lon = city.sample(n * 6, rng, job_mix=0.3)
        w = city.density(lat, lon, "apartments") + 1e-6
        pick = rng.choice(lat.size, n, replace=False, p=w / w.sum())
        return lat[pick], lon[pick]
