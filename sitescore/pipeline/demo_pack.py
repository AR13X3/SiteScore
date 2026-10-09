"""A committed snapshot of the processed real data, so a fresh clone works offline.

`python run.py data --make-demo-pack` copies every real table from the store into
data/demo-pack/ (zstd parquet + manifest). On startup, any table with no data at
all is restored from the pack before falling back to mock, so a fresh clone runs
on real data without the ~40-minute first fetch. Restored rows keep their dating,
so the as-of view and the backtest behave exactly as on the machine that made it.

Google Places is never packed: its terms don't allow storing results for long or
redistributing them.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from sitescore.config import load_sources
from sitescore.datastore import TABLES, DataStore
from sitescore.paths import ROOT

PACK_DIR = ROOT / "data" / "demo-pack"
NEVER_PACKED = {"places"}  # Google Places: terms forbid long-term storage and redistribution


def make(store: DataStore, pack_dir: Path = PACK_DIR, today: dt.date | None = None) -> dict:
    """Write the store's real tables into the pack; returns the manifest."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    manifest: dict = {"created": str(today or dt.date.today()), "tables": {}}  # noqa: DTZ011
    for name, spec in TABLES.items():
        stale = pack_dir / f"{name}.parquet"
        if name in NEVER_PACKED or store.provenance(name) != "real":
            stale.unlink(missing_ok=True)
            continue
        df = store.read(name)
        df.to_parquet(stale, index=False, compression="zstd")
        src = sources[spec.source]
        manifest["tables"][name] = {
            "rows": len(df),
            "published_range": [str(df["published_at"].min().date()),
                                str(df["published_at"].max().date())],
            "source": src.title, "licence": src.licence,
        }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def manifest(pack_dir: Path = PACK_DIR) -> dict | None:
    path = pack_dir / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def restore(store: DataStore, pack_dir: Path = PACK_DIR, only_missing: bool = True
            ) -> list[tuple[str, int]]:
    """Copy pack tables into the store as real data.

    only_missing=True touches only tables with no data at all, so data you fetched
    yourself (or mock you generated on purpose) is never overwritten.
    """
    info = manifest(pack_dir)
    if info is None:
        return []
    restored = []
    for name in info["tables"]:
        if name in NEVER_PACKED or name not in TABLES:
            continue
        if only_missing and store.has(name):
            continue
        df = pd.read_parquet(pack_dir / f"{name}.parquet")
        store.write(name, df, "real", note=f"from the demo pack ({info['created']})")
        restored.append((name, len(df)))
    return restored
