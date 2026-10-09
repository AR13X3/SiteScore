"""`python run.py data`: fetch and process every data source.

    python run.py data                 # real where possible, mock fallback per source
    python run.py data --mock          # regenerate mock data only
    python run.py data --only osm      # one source (repeatable)
    python run.py data --make-demo-pack     # snapshot real tables into data/demo-pack/
    python run.py data --restore-demo-pack  # load the pack (only tables with no data)
"""

from __future__ import annotations

import argparse
import logging
import time

from sitescore.datastore import DataStore
from sitescore.pipeline import ADAPTERS, demo_pack, run_all
from sitescore.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="python run.py data")
    parser.add_argument("--mock", action="store_true", help="only (re)generate mock data")
    parser.add_argument("--only", action="append", choices=[a.source_id for a in ADAPTERS],
                        help="run just this source (repeatable)")
    parser.add_argument("--make-demo-pack", action="store_true",
                        help="copy the real tables into data/demo-pack/ (to commit)")
    parser.add_argument("--restore-demo-pack", action="store_true",
                        help="load data/demo-pack/ into tables that have no data yet")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    store = DataStore(force_mock=get_settings().force_mock)
    if args.make_demo_pack:
        made = demo_pack.make(store)
        for name, t in made["tables"].items():
            print(f"{name:<18} {t['rows']:>8} rows  published {t['published_range'][0]} .. "
                  f"{t['published_range'][1]}")
        print(f"\nDemo pack written to {demo_pack.PACK_DIR} ({made['created']})")
        return
    if args.restore_demo_pack:
        restored = demo_pack.restore(store)
        for name, rows in restored:
            print(f"{name:<18} {rows:>8} rows restored")
        print("Nothing to restore: every table already has data." if not restored else "")
        return
    t0 = time.perf_counter()
    results = run_all(store, mock_only=args.mock, only=set(args.only) if args.only else None)
    print(f"\n{'source':<22} {'table':<15} {'data':<5} {'rows':>8}  note")
    for r in results:
        print(f"{r.source_id:<22} {r.table:<15} {r.provenance:<5} {r.rows:>8}  {r.note}")
    print(f"\nDone in {time.perf_counter() - t0:.1f}s. Store: {store.root}")


if __name__ == "__main__":
    main()
