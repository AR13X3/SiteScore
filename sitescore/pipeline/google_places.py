"""Google Places (optional) -> `places`: rating, review count, open/closed, as of today.

Outcome data. Ratings and review counts are only available as of the day we
fetch them, so this table is never visible to the model (TableSpec.model_visible
is False); the backtest scorer reads it after the predictions are made.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.mock_world import mock_world

# Business types whose venues we score in backtests.
SCORED_KINDS = ("cafe", "gym", "childcare")


class GooglePlaces(Adapter):
    source_id = "google_places"
    tables = ("places",)

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        if not ctx.settings.google_places_api_key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY not set")
        raise NotImplementedError("real adapter not built yet")

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        world = mock_world(ctx)
        rng = np.random.default_rng(ctx.seed("places"))
        today = pd.Timestamp(ctx.today)
        frames = []
        for key in SCORED_KINDS:
            _, h = world.venues[key]
            # Google keeps permanently closed places listed; drop ones closed long ago.
            h = h[h["close"].isna() | (h["close"] >= pd.Timestamp("2019-01-01"))]
            end = h["close"].fillna(today)
            # Reviews accrue while open; Google reviews only really took off ~2014.
            months_active = ((end - h["open"].clip(lower=pd.Timestamp("2014-01-01"))).dt.days
                             / 30.4).clip(lower=1)
            perf = h["performance"].to_numpy()
            rate = np.exp(0.9 + 0.6 * perf + rng.normal(0, 0.3, len(h)))  # reviews per month
            frames.append(pd.DataFrame({
                "place_id": "mock-place-" + h["venue_id"],
                "osm_id": "mock:" + h["venue_id"],
                "name": h["name"],
                "lon": h["lon"],
                "lat": h["lat"],
                "rating": np.clip(4.25 + 0.25 * perf + rng.normal(0, 0.2, len(h)), 2.5, 5.0).round(1),
                "review_count": rng.poisson(months_active.to_numpy() * rate),
                "business_status": np.where(h["close"].isna(), "OPERATIONAL", "CLOSED_PERMANENTLY"),
            }))
        df = pd.concat(frames, ignore_index=True)
        return {"places": stamp(df, published_at=today, valid_from=today, version=today)}
