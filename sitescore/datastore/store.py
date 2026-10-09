"""Parquet-backed store of canonical tables.

Each table can have two variants on disk: `<table>.real.parquet` (from the real
source) and `<table>.mock.parquet` (synthetic fallback). Reads use the real one
when present, so data fetched once keeps working offline; mock is the fallback.
SITESCORE_FORCE_MOCK=1 forces mock everywhere (demo safety switch).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Literal

import pandas as pd

from sitescore.datastore.asof import AsOfView
from sitescore.datastore.schema import DATING_COLUMNS, TABLES, TableSpec
from sitescore.paths import PROCESSED_DIR

Provenance = Literal["real", "mock"]


class SchemaError(ValueError):
    """A frame doesn't match its canonical table spec."""


def validate_frame(spec: TableSpec, df: pd.DataFrame) -> pd.DataFrame:
    """Check required columns and dating rules; return the frame with normalised dates."""
    missing = [c for c in spec.required_columns if c not in df.columns]
    if missing:
        raise SchemaError(f"{spec.name}: missing columns {missing}")
    df = df.copy()
    date_cols = [*DATING_COLUMNS, *(["version"] if spec.kind == "latest" else [])]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col]).astype("datetime64[ns]")
    if df["published_at"].isna().any():
        raise SchemaError(f"{spec.name}: every row needs published_at")
    if df["valid_from"].isna().any():
        raise SchemaError(f"{spec.name}: every row needs valid_from")
    if (df["published_at"] < df["valid_from"]).any():
        raise SchemaError(f"{spec.name}: rows published before the period they describe")
    if spec.kind == "latest" and df["version"].isna().any():
        raise SchemaError(f"{spec.name}: every row needs a version")
    return df


class DataStore:
    def __init__(self, root: Path = PROCESSED_DIR, force_mock: bool = False):
        self.root = Path(root)
        self.force_mock = force_mock
        self._cache: dict[Path, tuple[float, pd.DataFrame]] = {}

    # --- writing (pipeline only) ---------------------------------------------------

    def write(self, table: str, df: pd.DataFrame, provenance: Provenance, note: str = "") -> None:
        df = validate_frame(TABLES[table], df)
        self.root.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self._path(table, provenance), index=False)
        catalog = self.catalog()
        catalog.setdefault(table, {})[provenance] = {
            "rows": len(df),
            "written_at": dt.datetime.now().isoformat(timespec="seconds"),  # noqa: DTZ005 (local time)
            "published_range": [str(df["published_at"].min().date()),
                                str(df["published_at"].max().date())],
            "note": note,
        }
        (self.root / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    # --- reading -------------------------------------------------------------------

    def provenance(self, table: str) -> Provenance | None:
        if not self.force_mock and self._path(table, "real").exists():
            return "real"
        if self._path(table, "mock").exists():
            return "mock"
        return None

    def has(self, table: str) -> bool:
        return self.provenance(table) is not None

    def read(self, table: str) -> pd.DataFrame:
        """Full, unfiltered table. The model must use as_of() instead."""
        prov = self.provenance(table)
        if prov is None:
            raise FileNotFoundError(f"no data for table '{table}'; run `python run.py data`")
        path = self._path(table, prov)
        mtime = path.stat().st_mtime
        cached = self._cache.get(path)
        if cached is None or cached[0] != mtime:
            cached = (mtime, pd.read_parquet(path))
            self._cache[path] = cached
        return cached[1]

    def as_of(self, date: dt.date) -> AsOfView:
        return AsOfView(self, date)

    def catalog(self) -> dict:
        path = self.root / "catalog.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _path(self, table: str, provenance: Provenance) -> Path:
        return self.root / f"{table}.{provenance}.parquet"
