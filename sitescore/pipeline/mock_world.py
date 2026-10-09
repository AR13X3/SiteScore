"""Shared mock state: one MockCity and one set of venue histories per region and day.

The OSM mock (where venues are) and the Google Places mock (how they performed)
must describe the same venues, so both read from here.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sitescore.pipeline.base import PipelineContext
from sitescore.pipeline.mock_city import VENUE_KINDS, MockCity, VenueKind


@dataclass
class MockWorld:
    city: MockCity
    venues: dict[str, tuple[VenueKind, pd.DataFrame]]


_cache: dict[tuple[str, dt.date], MockWorld] = {}


def mock_world(ctx: PipelineContext) -> MockWorld:
    key = (ctx.region.id, ctx.today)
    if key not in _cache:
        city = MockCity(ctx.region)
        venues = {
            kind.key: (kind, city.venue_history(
                kind, np.random.default_rng(ctx.seed(f"venues:{kind.key}")), ctx.today))
            for kind in VENUE_KINDS
        }
        _cache[key] = MockWorld(city, venues)
    return _cache[key]
