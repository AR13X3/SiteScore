"""Source adapters and the pipeline runner.

Each adapter turns one source into canonical tables (see datastore/schema.py).
It has two ways to do that:

    fetch(ctx)  download and process the real source
    mock(ctx)   generate synthetic data with the same columns and the same dating

The runner tries fetch() and falls back to mock() on any failure, recording why,
so the app always has data and the UI can show which tables are real.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pandas as pd

from sitescore.config import Region, Source, load_region, load_sources
from sitescore.datastore import DataStore
from sitescore.paths import raw_dir
from sitescore.settings import Settings, get_settings

log = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    region: Region
    sources: dict[str, Source]
    settings: Settings
    raw_dir: Path
    today: dt.date
    snapshot_dates: list[dt.date] = field(default_factory=list)
    # The store being filled, for adapters that build on another source's output.
    store: DataStore | None = None

    def source(self, source_id: str) -> Source:
        return self.sources[source_id]

    def published(self, source_id: str) -> dt.date:
        """Publication date of a fixed-date release (e.g. a Census)."""
        pub = self.source(source_id).published_at
        if pub.date is None:
            raise ValueError(f"{source_id} has no fixed publication date")
        return pub.date

    def seed(self, name: str) -> int:
        """Stable per-name seed so every mock table is reproducible."""
        return zlib.crc32(f"{self.region.id}:{name}".encode())


def build_context(today: dt.date | None = None) -> PipelineContext:
    sources = load_sources()
    today = today or dt.date.today()  # noqa: DTZ011 (local calendar date is intended)
    return PipelineContext(
        region=load_region(),
        sources=sources,
        settings=get_settings(),
        raw_dir=raw_dir(),
        today=today,
        snapshot_dates=snapshot_dates(sources["osm"], today),
    )


def snapshot_dates(osm: Source, today: dt.date) -> list[dt.date]:
    spec = getattr(osm, "snapshots", None) or {"start": "2019-01-01", "every_months": 3}
    start = pd.Timestamp(spec["start"])
    dates = pd.date_range(start, pd.Timestamp(today), freq=f"{int(spec['every_months'])}MS")
    return sorted({d.date() for d in dates} | {today})


def stamp(df: pd.DataFrame, *, published_at, valid_from, valid_to=None, version=None
          ) -> pd.DataFrame:
    """Attach dating columns. Each argument may be a scalar or a per-row sequence."""
    df = df.copy()
    df["published_at"] = published_at
    df["valid_from"] = valid_from
    df["valid_to"] = pd.NaT if valid_to is None else valid_to
    if version is not None:
        df["version"] = version
    return df


class Adapter(ABC):
    source_id: ClassVar[str]
    tables: ClassVar[tuple[str, ...]]

    def fetch(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]:
        raise NotImplementedError("real adapter not built yet")

    @abstractmethod
    def mock(self, ctx: PipelineContext) -> dict[str, pd.DataFrame]: ...


@dataclass(frozen=True)
class RunResult:
    source_id: str
    table: str
    provenance: str
    rows: int
    note: str


def run_adapter(adapter: Adapter, store: DataStore, ctx: PipelineContext,
                mock_only: bool = False, reason: str = "mock requested") -> list[RunResult]:
    note = ""
    if mock_only:
        note = reason
    elif ctx.settings.offline:
        note = "offline mode"
    else:
        try:
            frames = adapter.fetch(dataclasses.replace(ctx, store=store))
            return _write(adapter, store, frames, "real", "fetched")
        except NotImplementedError as exc:
            note = str(exc)
        except Exception as exc:  # noqa: BLE001 - any source failure -> mock, never a broken demo
            log.warning("%s fetch failed, using mock: %s", adapter.source_id, exc)
            note = f"fetch failed: {type(exc).__name__}: {exc}"[:300]
    return _write(adapter, store, adapter.mock(ctx), "mock", note)


def _write(adapter: Adapter, store: DataStore, frames: dict[str, pd.DataFrame],
           provenance: str, note: str) -> list[RunResult]:
    unexpected = set(frames) - set(adapter.tables)
    if unexpected:
        raise ValueError(f"{adapter.source_id} produced unexpected tables {unexpected}")
    results = []
    for table, df in frames.items():
        store.write(table, df, provenance, note)  # type: ignore[arg-type]
        results.append(RunResult(adapter.source_id, table, provenance, len(df), note))
    return results
