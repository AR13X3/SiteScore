"""`python run.py data`: fetch and process every data source.

    python run.py data                 # real where possible, mock fallback per source
    python run.py data --mock          # regenerate mock data only
    python run.py data --only osm      # one source (repeatable)
"""

from __future__ import annotations

import argparse
import logging
import time

from sitescore.datastore import DataStore
from sitescore.pipeline import ADAPTERS, run_all
from sitescore.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="python run.py data")
    parser.add_argument("--mock", action="store_true", help="only (re)generate mock data")
    parser.add_argument("--only", action="append", choices=[a.source_id for a in ADAPTERS],
                        help="run just this source (repeatable)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    store = DataStore(force_mock=get_settings().force_mock)
    t0 = time.perf_counter()
    results = run_all(store, mock_only=args.mock, only=set(args.only) if args.only else None)
    print(f"\n{'source':<22} {'table':<15} {'data':<5} {'rows':>8}  note")
    for r in results:
        print(f"{r.source_id:<22} {r.table:<15} {r.provenance:<5} {r.rows:>8}  {r.note}")
    print(f"\nDone in {time.perf_counter() - t0:.1f}s. Store: {store.root}")


if __name__ == "__main__":
    main()
