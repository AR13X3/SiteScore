"""The as-of view: the model's only way to read data.

A model run "as of" date D gets an AsOfView(D). It filters every table to rows
published on or before D, then checks the result again before handing it over,
so a bug in the filter fails loudly instead of quietly leaking the future.
It also logs what was read, so every result can show which data it was built on.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from sitescore.datastore.schema import TABLES

if TYPE_CHECKING:
    from sitescore.datastore.store import DataStore


class LeakageError(RuntimeError):
    """The model tried to read data that wasn't public on the as-of date."""


class NoDataAsOf(LookupError):
    """A table has no release published on or before the as-of date."""


@dataclass(frozen=True)
class Access:
    table: str
    provenance: str  # "real" | "mock"
    rows: int
    version: dt.date | None  # release/snapshot used, for "latest" tables
    latest_published: dt.date | None


class AsOfView:
    def __init__(self, store: DataStore, as_of: dt.date):
        self._store = store
        self._as_of = as_of
        self._cutoff = pd.Timestamp(as_of)
        self._accessed: dict[str, Access] = {}

    @property
    def as_of(self) -> dt.date:
        return self._as_of

    def table(self, name: str) -> pd.DataFrame:
        spec = TABLES[name]
        if not spec.model_visible:
            raise LeakageError(
                f"'{name}' is outcome data (only known today); the model may not read it"
            )
        df = self._store.read(name)
        df = df[df["published_at"] <= self._cutoff]
        version = None
        if spec.kind == "latest":
            if df.empty:
                earliest = self._store.read(name)["published_at"].min()
                raise NoDataAsOf(
                    f"no '{name}' release published on or before {self._as_of} "
                    f"(earliest available: {earliest.date() if pd.notna(earliest) else 'none'})"
                )
            newest = df["version"].max()
            df = df[df["version"] == newest]
            version = newest.date()
        df = df[(df["valid_from"] <= self._cutoff)
                & (df["valid_to"].isna() | (df["valid_to"] > self._cutoff))]

        # Belt and braces: re-check the invariant on what we're about to return.
        if (df["published_at"] > self._cutoff).any():
            raise LeakageError(f"'{name}' contains rows published after {self._as_of}")

        latest = df["published_at"].max()
        self._accessed[name] = Access(
            table=name,
            provenance=self._store.provenance(name) or "unknown",
            rows=len(df),
            version=version,
            latest_published=latest.date() if pd.notna(latest) else None,
        )
        return df.reset_index(drop=True).copy()

    @property
    def accessed(self) -> list[Access]:
        """Every table read through this view: provenance, rows, newest data used."""
        return list(self._accessed.values())
