"""Transport for NSW station entries/exits -> `station_usage` (station x month)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from sitescore.pipeline.base import Adapter, PipelineContext, stamp
from sitescore.pipeline.mock_city import STATIONS

FIRST_MONTH = dt.date(2016, 7, 1)
# Typical monthly pattern of rail patronage (Jan..Dec): summer holidays dip.
_SEASON = np.array([0.82, 0.97, 1.04, 0.97, 1.04, 1.01, 1.0, 1.04, 1.02, 1.02, 1.04, 0.93])


def _covid_factor(month: dt.date) -> float:
    """Approximate shape of Sydney rail patronage through COVID (mock only)."""
    steps = [
        (dt.date(2020, 3, 1), 0.60), (dt.date(2020, 4, 1), 0.22), (dt.date(2020, 6, 1), 0.45),
        (dt.date(2020, 10, 1), 0.60), (dt.date(2021, 7, 1), 0.28), (dt.date(2021, 11, 1), 0.55),
        (dt.date(2022, 3, 1), 0.72), (dt.date(2023, 1, 1), 0.85), (dt.date(2024, 1, 1), 0.92),
    ]
    factor = 1.0
    for start, value in steps:
        if month >= start:
            factor = value
    return factor


class TfnswStations(Adapter):
    source_id = "tfnsw_station_usage"
    tables = ("station_usage",)

    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        rng = np.random.default_rng(ctx.seed("station_usage"))
        lag = pd.Timedelta(days=ctx.source(self.source_id).published_at.lag_days or 0)
        months = pd.date_range(FIRST_MONTH, ctx.today, freq="MS")
        rows = []
        for st in STATIONS:
            for m in months:
                month = m.date()
                if (st.opened and month < st.opened.replace(day=1)) or (st.closed and month >= st.closed):
                    continue
                years = (month - FIRST_MONTH).days / 365.25
                level = (st.monthly_exits * _SEASON[month.month - 1] * _covid_factor(month)
                         * 1.012 ** years * rng.normal(1, 0.03))
                rows.append({"station": st.name, "lon": st.lon, "lat": st.lat, "month": m,
                             "exits": round(level), "entries": round(level * rng.normal(0.99, 0.01))})
        df = pd.DataFrame(rows)
        month_end = df["month"] + pd.offsets.MonthEnd(0)
        df = stamp(df, published_at=month_end + lag, valid_from=df["month"],
                   valid_to=df["month"] + pd.offsets.MonthBegin(1))
        # Months not yet published as of today don't exist yet.
        return {"station_usage": df[df["published_at"] <= pd.Timestamp(ctx.today)]}
