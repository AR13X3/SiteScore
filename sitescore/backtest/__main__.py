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
    s = result.survival

    print(f"\nBacktest '{result.cohort}' ({result.business_type}), run {result.run_on}; "
          f"data: {', '.join(f'{k}={v}' for k, v in result.provenance.items())}")
    print(f"{'#':>3}  {'business':<26} {'opened':<10} {'opening':<10} {'predicted':>10}  "
          f"{'actual #':>8}  {'today':<6} {s.horizon_months}-month outcome")
    for r in result.rows:
        today = {True: "open", False: "closed", None: "?"}[r.actual.still_open]
        h = r.actual.horizon
        fate = "-" if h is None else h.status + (f" ({h.kind})" if h.kind and h.status == "closed"
                                                 else "")
        print(f"{r.predicted_rank:>3}  {r.name[:26]:<26} {r.opened!s:<10} "
              f"{r.opening_check or '-':<10} ${r.predicted_score / 1e6:>8.2f}M  "
              f"{r.actual_rank or '-':>8}  {today:<6} {fate}")
    a = result.accuracy
    checks = ", ".join(f"{v} {k}" for k, v in sorted(result.opening_checks.items()))
    print(f"\n{a.n} businesses scored, {len(result.skipped)} skipped"
          + (f"; opening check over the discovered cohort: {checks}" if checks else ""))
    print("Actual performance (combined proxies):")
    print(f"  pairs ranked correctly: model {_pct(a.pairwise_accuracy)} vs foot-traffic-only "
          f"{_pct(a.baseline_pairwise_accuracy)}  (50% = coin flip, {a.pairs} pairs)")
    print(f"  Spearman: model {_num(a.spearman)} vs {_num(a.baseline_spearman)}")
    counts = ", ".join(f"{v} {k}" for k, v in s.status_counts.items())
    kinds = ", ".join(f"{v} {k}" for k, v in s.closure_kinds.items()) or "none"
    print(f"\nSurvival at {s.horizon_months} months (secondary): {counts}; closures: {kinds}")
    print(f"  survivors ranked above closures (AUC): model {_num(s.auc)} vs "
          f"{_num(s.baseline_auc)}")
    for label, table in (("model", s.by_third), ("foot traffic only", s.baseline_by_third)):
        cells = "  ".join(f"{t.third} {t.closed}/{t.judged}"
                          + (f" ({t.closure_rate:.0%})" if t.closure_rate is not None else "")
                          for t in table)
        print(f"  closed / judged by predicted third, {label}: {cells}")
    for label, table in (("model", s.by_third), ("foot traffic only", s.baseline_by_third)):
        churn = "  ".join(f"{t.third} {t.mean_site_closures:.2f}" for t in table
                          if t.mean_site_closures is not None)
        print(f"  café closures at the same spot since 2019, mean by predicted third, "
              f"{label}: {churn}")
    print(f"  spots without closures ranked above spots with (AUC): model "
          f"{_num(s.site_churn_auc)} vs {_num(s.baseline_site_churn_auc)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{result.cohort}_{result.business_type}_{dt.date.today()}.json"  # noqa: DTZ011
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
