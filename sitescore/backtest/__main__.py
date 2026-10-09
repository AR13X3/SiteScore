"""`python run.py backtest`: predict past openings with past data and score against reality.

    python run.py backtest                    # cohort discovered from OSM history
    python run.py backtest --cohort demo      # backtests/cohorts/demo.csv
    python run.py backtest --limit 3          # first 3 businesses only
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from sitescore.backtest import OSM_COHORT, backtest
from sitescore.datastore import DataStore
from sitescore.paths import ROOT
from sitescore.settings import get_settings

RESULTS_DIR = ROOT / "backtests" / "results"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _num(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python run.py backtest")
    parser.add_argument("--cohort", default=OSM_COHORT,
                        help="'osm' (discover from OSM history) or a CSV name in backtests/cohorts")
    parser.add_argument("--type", default="cafe", help="business type")
    parser.add_argument("--limit", type=int, help="only the first N businesses")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    store = DataStore(force_mock=get_settings().force_mock)
    result = backtest(args.cohort, store, args.type, limit=args.limit)

    print(f"\nBacktest '{result.cohort}' ({result.business_type}), run {result.run_on}; "
          f"data: {', '.join(f'{k}={v}' for k, v in result.provenance.items())}")
    print(f"{'#':>3}  {'business':<28} {'opened':<10} {'data to':<10} {'predicted':>10}  "
          f"{'actual #':>8}  status")
    for r in result.rows:
        status = {True: "open", False: "closed", None: "?"}[r.actual.still_open]
        print(f"{r.predicted_rank:>3}  {r.name[:28]:<28} {r.opened!s:<10} {r.data_cutoff!s:<10} "
              f"${r.predicted_score / 1e6:>8.2f}M  {r.actual_rank or '-':>8}  {status}")
    a = result.accuracy
    print(f"\n{a.n} businesses scored, {len(result.skipped)} skipped; {a.closures} closed")
    print(f"  pairs ranked correctly: model {_pct(a.pairwise_accuracy)} vs foot-traffic-only "
          f"{_pct(a.baseline_pairwise_accuracy)}  (50% = coin flip, {a.pairs} pairs)")
    print(f"  Spearman: model {_num(a.spearman)} vs {_num(a.baseline_spearman)}")
    print(f"  survivors ranked above closures (AUC): model {_num(a.survival_auc)} vs "
          f"{_num(a.baseline_survival_auc)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{result.cohort}_{result.business_type}_{dt.date.today()}.json"  # noqa: DTZ011
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
