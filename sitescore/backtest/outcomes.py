"""Phase 2 of a backtest: how each business actually did (read only after predicting).

Proxies, from what open data allows:
- survival: still on today's OpenStreetMap (and not renamed or tagged disused);
  Google's business_status overrides when available;
- weekly opening hours: first mapped vs latest (cutting hours is a warning sign);
- reviews per month since opening and rating (Google Places, when the places
  table describes the same world as the map: real with real, mock with mock).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from sitescore.backtest.cohort import Business
from sitescore.datastore import DataStore

DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]


def weekly_hours(spec: str | None) -> float | None:
    """Hours open per week from common OSM opening_hours strings, else None.

    Handles 'Mo-Fr 07:00-15:00; Sa,Su 08:00-14:00', 'Mo-Su 06:30-15:30',
    '07:00-17:00' (every day), '24/7' and wrapping ranges like 'Fr-We'.
    Public-holiday rules are ignored.
    """
    if not spec:
        return None
    s = spec.strip().lower()
    if s == "24/7":
        return 168.0
    days: dict[str, float] = {}
    for m in _RULE.finditer(s):
        day_part, time_part = m.group("days"), m.group("times").strip()
        targets = _expand_days(day_part)
        if day_part and not targets:
            continue  # public-holiday-only rule
        if time_part in ("off", "closed"):
            hours = 0.0
        else:
            hours = 0.0
            for h1, m1, h2, m2 in _SPAN.findall(time_part):
                start, end = int(h1) + int(m1) / 60, int(h2) + int(m2) / 60
                hours += (end - start) % 24 or 24
        for d in targets:
            days[d] = hours  # later rules override earlier ones, as in OSM
    return float(sum(days.values())) if days else None


_DAY = r"(?:mo|tu|we|th|fr|sa|su|ph)"
_SPAN = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
_RULE = re.compile(
    rf"(?P<days>(?:{_DAY}(?:\s*-\s*{_DAY})?\s*,?\s*)+)?\s*"
    r"(?P<times>(?:\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*,?\s*)+|off|closed)"
)


def _expand_days(part: str | None) -> list[str]:
    """'mo-fr,su' -> ['mo',...,'fr','su']; None -> every day; 'ph' alone -> []."""
    if not part:
        return DAYS
    out = []
    for token in re.split(r"\s*,\s*", part.strip(" ,")):
        if not token or token == "ph":
            continue
        if "-" in token:
            a, b = (DAYS.index(x.strip()) for x in token.split("-"))
            out += [DAYS[(a + i) % 7] for i in range((b - a) % 7 + 1)]
        else:
            out.append(token)
    return out


@dataclass(frozen=True)
class Outcome:
    still_open: bool | None
    status_source: str            # "osm", "google" or "unknown"
    months_open: float
    reviews: int | None = None
    reviews_per_month: float | None = None
    rating: float | None = None
    hours_first: float | None = None
    hours_latest: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def hours_change(self) -> float | None:
        if self.hours_first and self.hours_latest is not None:
            return self.hours_latest / self.hours_first - 1
        return None


def observe(businesses: list[Business], store: DataStore, today: dt.date) -> dict[str, Outcome]:
    """Outcome per business, keyed by osm_id or name."""
    pois = store.read("pois")
    latest_version = pois["version"].max()
    latest = pois[pois["version"] == latest_version].set_index("osm_id")
    history = pois.sort_values("version").groupby("osm_id")
    places = _matching_places(store)
    out = {}
    for b in businesses:
        notes: list[str] = []
        months = max((today - b.opened).days / 30.44, 0.5)
        still_open, source = None, "unknown"
        hours_first = hours_latest = None
        if b.osm_id and b.osm_id in history.groups:
            rows = history.get_group(b.osm_id)
            tags = [json.loads(t) for t in rows["tags"]]
            hours = [weekly_hours(t.get("opening_hours")) for t in tags]
            known = [h for h in hours if h is not None]
            if len(known) >= 2:
                hours_first, hours_latest = known[0], known[-1]
            still_open, source = _osm_status(b, latest, notes), "osm"
        place = _find_place(b, places)
        if place is not None:
            status = place["business_status"]
            if status in ("CLOSED_PERMANENTLY", "OPERATIONAL"):
                still_open, source = status == "OPERATIONAL", "google"
            reviews = int(place["review_count"])
            out_key = b.osm_id or b.name
            out[out_key] = Outcome(still_open, source, months, reviews, reviews / months,
                                   float(place["rating"]), hours_first, hours_latest, notes)
            continue
        out[b.osm_id or b.name] = Outcome(still_open, source, months, hours_first=hours_first,
                                          hours_latest=hours_latest, notes=notes)
    return out


def _osm_status(b: Business, latest: pd.DataFrame, notes: list[str]) -> bool:
    if b.osm_id not in latest.index:
        notes.append("no longer on OpenStreetMap")
        return False
    row = latest.loc[b.osm_id]
    tags = json.loads(row["tags"])
    if any(k.startswith(("disused:", "was:", "closed:")) for k in tags):
        notes.append("tagged disused/closed on OpenStreetMap")
        return False
    if row["name"] and b.name and row["name"].strip().lower() != b.name.strip().lower():
        notes.append(f"now '{row['name']}' on OpenStreetMap (replaced)")
        return False
    return True


def _matching_places(store: DataStore) -> pd.DataFrame | None:
    """The Google places table, only if it describes the same world as the map."""
    if not store.has("places") or store.provenance("places") != store.provenance("pois"):
        return None
    return store.read("places")


def _find_place(b: Business, places: pd.DataFrame | None) -> pd.Series | None:
    """The business's own Google record. Matching the OSM id isn't enough on its own:
    if the shop was replaced, that record describes the new occupant."""
    if places is None:
        return None
    name = b.name.strip().lower()
    same_name = places["name"].str.strip().str.lower() == name
    if b.osm_id:
        hit = places[(places["osm_id"] == b.osm_id) & same_name]
        if len(hit):
            return hit.iloc[0]
    d = np.hypot((places["lon"] - b.lon) * 92_600, (places["lat"] - b.lat) * 110_500)
    near = places[(d <= 60) & same_name]
    return near.iloc[0] if len(near) else None
