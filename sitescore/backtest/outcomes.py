"""Phase 2 of a backtest: how each business actually did (read only after predicting).

Proxies, from what open data allows:
- survival: a weighted vote of every source that knows the business (OSM,
  Overture, Foursquare, ASIC business names, Google) -> survival score -1..+1;
- weekly opening hours: first mapped vs latest (cutting hours is a warning sign);
- reviews per month since opening and rating (Google Places, when the places
  table describes the same world as the map: real with real, mock with mock).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from dataclasses import dataclass, field

import pandas as pd

from sitescore.backtest.cohort import Business
from sitescore.datastore import DataStore
from sitescore.matching import best_match, distance_m, normalise_name, same_business

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
class Evidence:
    """One source's view on whether a business is still trading."""

    source: str
    open: bool
    weight: float          # after scaling by confidence and by age
    detail: str
    as_of: dt.date | None = None


@dataclass(frozen=True)
class Outcome:
    still_open: bool | None        # weighted vote across sources (None: no evidence)
    survival_score: float | None   # (open - closed) / total weight, -1..+1
    evidence: list[Evidence]
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

    @property
    def status_source(self) -> str:
        return ", ".join(sorted({e.source for e in self.evidence})) or "unknown"


@dataclass
class _Sources:
    """Outcome tables that describe the same world as the map (real with real)."""

    pois: pd.DataFrame
    latest: pd.DataFrame
    places: pd.DataFrame | None
    overture: pd.DataFrame | None
    fsq: pd.DataFrame | None
    names: pd.DataFrame | None

    @classmethod
    def load(cls, store: DataStore) -> _Sources:
        pois = store.read("pois")
        world = store.provenance("pois")

        def same_world(table: str) -> pd.DataFrame | None:
            ok = store.has(table) and store.provenance(table) == world
            return store.read(table) if ok else None

        return cls(pois, pois[pois["version"] == pois["version"].max()].set_index("osm_id"),
                   same_world("places"), same_world("overture_places"), same_world("fsq_places"),
                   same_world("business_names"))


def observe(businesses: list[Business], store: DataStore, today: dt.date,
            weights: dict[str, float] | None = None, asic_window: tuple[int, int] = (18, 6),
            half_life_months: float = 12.0) -> dict[str, Outcome]:
    """Outcome per business, keyed by osm_id or name."""
    w = {"google": 3.0, "osm_closed": 2.0, "osm_open": 1.0, "overture": 1.0,
         "foursquare": 1.0, "asic": 0.75, **(weights or {})}
    src = _Sources.load(store)
    history = src.pois.sort_values("version").groupby("osm_id")
    out = {}
    for b in businesses:
        notes: list[str] = []
        hours_first = hours_latest = None
        if b.osm_id and b.osm_id in history.groups:
            hours = [weekly_hours(json.loads(t).get("opening_hours"))
                     for t in history.get_group(b.osm_id)["tags"]]
            known = [h for h in hours if h is not None]
            if len(known) >= 2:
                hours_first, hours_latest = known[0], known[-1]
        place = _find_place(b, src.places)
        evidence = [_aged(e, today, half_life_months) for e in (
            _osm(b, src, history, w["osm_open"], w["osm_closed"]),
            _google(place, w["google"]),
            _overture(b, src.overture, w["overture"]),
            _foursquare(b, src.fsq, w["foursquare"]),
            _asic(b, src.names, w["asic"], asic_window),
        ) if e is not None and e.weight > 0]
        evidence = [e for e in evidence if e.weight > 1e-6]
        still_open, score = _vote(evidence)
        notes += [f"{e.source}: {e.detail}" for e in evidence]
        months = max((today - b.opened).days / 30.44, 0.5)
        reviews = int(place["review_count"]) if place is not None else None
        out[b.osm_id or b.name] = Outcome(
            still_open, score, evidence, months, reviews,
            None if reviews is None else reviews / months,
            None if place is None else float(place["rating"]), hours_first, hours_latest, notes)
    return out


def _aged(e: Evidence, today: dt.date, half_life_months: float) -> Evidence:
    """Discount an observation by how long ago its data was collected."""
    if e.as_of is None:
        return e
    months = max((today - e.as_of).days / 30.44, 0.0)
    return dataclasses.replace(e, weight=e.weight * 0.5 ** (months / half_life_months))


def _vote(evidence: list[Evidence]) -> tuple[bool | None, float | None]:
    total = sum(e.weight for e in evidence)
    if total == 0:
        return None, None
    score = sum(e.weight if e.open else -e.weight for e in evidence) / total
    return (None if score == 0 else score > 0), score


def _osm(b: Business, src: _Sources, history, w_open: float, w_closed: float
         ) -> Evidence | None:
    if not b.osm_id or b.osm_id not in history.groups:
        return None
    as_of = src.pois["version"].max().date()
    if b.osm_id not in src.latest.index:
        return Evidence("osm", False, w_closed, "removed from OpenStreetMap", as_of)
    row = src.latest.loc[b.osm_id]
    tags = json.loads(row["tags"])
    if any(k.startswith(("disused:", "was:", "closed:")) for k in tags):
        return Evidence("osm", False, w_closed, "tagged disused/closed on OpenStreetMap", as_of)
    if row["name"] and b.name and not same_business(row["name"], b.name):
        return Evidence("osm", False, w_closed,
                        f"now '{row['name']}' on OpenStreetMap (replaced)", as_of)
    renamed = row["name"] and row["name"].strip().lower() != b.name.strip().lower()
    return Evidence("osm", True, w_open, "still on OpenStreetMap"
                    + (f" (name now '{row['name']}')" if renamed else ""), as_of)


def _google(place: pd.Series | None, weight: float) -> Evidence | None:
    if place is None or place["business_status"] not in ("OPERATIONAL", "CLOSED_PERMANENTLY"):
        return None
    is_open = place["business_status"] == "OPERATIONAL"
    return Evidence("google", is_open, weight, f"Google: {place['business_status'].lower()}",
                    pd.Timestamp(place["version"]).date())


def _overture(b: Business, ov: pd.DataFrame | None, weight: float) -> Evidence | None:
    """Listed with high confidence = open; low confidence or missing = probably closed."""
    if ov is None:
        return None
    release = ov["version"].max()
    if pd.Timestamp(b.opened) > release - pd.DateOffset(months=3):
        return None  # too new for Overture to know either way
    m = best_match(b.name, b.lat, b.lon, ov, max_m=150)
    if m is None:
        return Evidence("overture", False, 0.4 * weight,
                        f"not listed in Overture ({release.date()})", release.date())
    if m["operating_status"] == "permanently_closed":
        return Evidence("overture", False, weight, "Overture: permanently closed",
                        release.date())
    conf = float(m["confidence"])
    if conf >= 0.5:
        return Evidence("overture", True, weight * conf,
                        f"listed in Overture (confidence {conf:.2f})", release.date())
    return Evidence("overture", False, weight * (1 - conf),
                    f"listed in Overture with low confidence ({conf:.2f})", release.date())


def _foursquare(b: Business, fsq: pd.DataFrame | None, weight: float) -> Evidence | None:
    if fsq is None:
        return None
    snapshot = fsq["version"].max()
    if pd.Timestamp(b.opened) > snapshot - pd.DateOffset(months=2):
        return None  # the snapshot predates (or barely follows) the opening
    m = best_match(b.name, b.lat, b.lon, fsq, max_m=150)
    if m is None:
        return None  # Foursquare coverage is partial: absence says little
    closed = m["date_closed"]
    if pd.notna(closed) and closed >= pd.Timestamp(b.opened) - pd.Timedelta(days=30):
        return Evidence("foursquare", False, weight,
                        f"marked closed {pd.Timestamp(closed).date()} (Foursquare)",
                        pd.Timestamp(closed).date())
    if pd.notna(closed):
        return None  # a previous business at the same spot
    refreshed = m["date_refreshed"]
    fresh = pd.notna(refreshed) and refreshed >= snapshot - pd.DateOffset(months=12)
    when = pd.Timestamp(refreshed).date() if pd.notna(refreshed) else "unknown"
    return Evidence("foursquare", True, weight * (1.0 if fresh else 0.5),
                    f"listed as of {snapshot.date()}, last refreshed {when}", snapshot.date())


def _asic(b: Business, names: pd.DataFrame | None, weight: float,
          window: tuple[int, int]) -> Evidence | None:
    """A unique exact business name registered around the opening date."""
    if names is None:
        return None
    key = normalise_name(b.name)
    same = names[names["bn_name"].map(normalise_name) == key]
    opened = pd.Timestamp(b.opened)
    lo, hi = opened - pd.DateOffset(months=window[0]), opened + pd.DateOffset(months=window[1])
    same = same[(same["registered"] >= lo) & (same["registered"] <= hi)]
    if len(same) != 1:
        return None
    row = same.iloc[0]
    reg = pd.Timestamp(row["registered"]).date()
    if str(row["status"]).lower().startswith("dereg"):
        cancelled = pd.Timestamp(row["cancelled"]).date() if pd.notna(row["cancelled"]) else "?"
        return Evidence("asic", False, weight,
                        f"business name registered {reg}, cancelled {cancelled} (ASIC)",
                        pd.Timestamp(row["version"]).date())
    return Evidence("asic", True, weight,
                    f"business name registered {reg}, still registered (ASIC)",
                    pd.Timestamp(row["version"]).date())


def _find_place(b: Business, places: pd.DataFrame | None) -> pd.Series | None:
    """The business's own Google record. Matching the OSM id isn't enough on its own:
    if the shop was replaced, that record describes the new occupant."""
    if places is None:
        return None
    same_name = places["name"].fillna("").map(lambda n: same_business(n, b.name))
    if b.osm_id:
        hit = places[(places["osm_id"] == b.osm_id) & same_name]
        if len(hit):
            return hit.iloc[0]
    d = distance_m(b.lat, b.lon, places["lat"].to_numpy(float), places["lon"].to_numpy(float))
    near = places[(d <= 60) & same_name]
    return near.iloc[0] if len(near) else None
