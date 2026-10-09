"""Phase 1 of a backtest: predict each business using only data public before it opened.

Leakage guards, on top of the AsOfView itself:
- the market is built from store.as_of(business.as_of), never from the store;
- the business is removed from its own competitor set;
- every data source the prediction touched is checked again: anything published
  after the as-of date raises LeakageError;
- this module never reads outcome data (a test enforces that).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sitescore.backtest.cohort import Business
from sitescore.config import BusinessProfile, Calendar, ModelConfig, Region
from sitescore.datastore import DataStore, LeakageError
from sitescore.model.market import build_market
from sitescore.model.simulate import simulate
from sitescore.model.types import DataUsed, Site


@dataclass(frozen=True)
class Prediction:
    business: Business
    score: float                 # projected revenue over the first score_months
    profit: float | None         # projected profit over them, with the site's estimated rent
    mature_monthly: float
    demand_only: float           # naive baseline: potential customers within walking distance
    layers: dict[str, float]
    data_used: list[DataUsed]

    @property
    def data_cutoff(self) -> dt.date | None:
        dates = [d.latest_published for d in self.data_used if d.latest_published]
        return max(dates) if dates else None


def predict(b: Business, store: DataStore, profile: BusinessProfile, cfg: ModelConfig,
            region: Region, calendar: Calendar, score_months: int) -> Prediction:
    view = store.as_of(b.as_of)
    exclude = (b.osm_id,) if b.osm_id else ()
    market = build_market(view, profile, cfg, region, exclude_osm_ids=exclude)
    site = Site(id=b.osm_id or b.name, label=b.name, lat=b.lat, lon=b.lon)
    open_date = max(b.opened, b.as_of)
    result = simulate(market, [site], profile, cfg, region, calendar, open_date).sites[0]

    for used in result.mature.data_used:  # second, independent check of the cut-off
        if used.latest_published and used.latest_published > b.as_of:
            raise LeakageError(f"{b.name}: '{used.table}' data from {used.latest_published} "
                               f"is after the as-of date {b.as_of}")
    if b.osm_id and b.osm_id in set(market.competitors.ids):
        raise LeakageError(f"{b.name} is in its own competitor set")

    layers = {layer.key: layer.factor for layer in result.mature.layers}
    months = result.months[:score_months]
    return Prediction(
        business=b,
        score=sum(m.revenue for m in months),
        profit=None if months[0].profit is None else sum(m.profit for m in months),
        mature_monthly=result.mature.monthly_revenue,
        demand_only=layers.get("demand", 0.0),
        layers=layers,
        data_used=result.mature.data_used,
    )
