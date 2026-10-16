"""Recorded analyst runs, for a hosted demo that has no language-model key.

A recording is one real run of the analyst: the question, then every event it streamed
(text, tool steps, map actions, the brief), each with the time it arrived. Replaying it
sends the same events in the same order, with the long waits (the model thinking, a
9-second spot search) shortened, so the demo shows exactly what the analyst did.

    python -m sitescore.analyst.replay record          # the standard questions
    python -m sitescore.analyst.replay record "Where should I open a café near Rosehill?"
    python -m sitescore.analyst.replay list

Recording needs OPENROUTER_API_KEY; replaying needs nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sitescore.paths import ROOT

REPLAY_DIR = ROOT / "data" / "analyst-replays"

# The questions the demo offers: the overview's examples and the analyst's suggestions.
STANDARD_QUESTIONS = [
    "Find the best café spot within 1 km of Parramatta station, ranked by profit",
    "Compare Church St Parramatta, Harris Park and Wentworth Point",
    "Are any vacant shopfronts near Westmead Hospital worth a look?",
    "How accurate is SiteScore? Should I trust it?",
]

# Waits between events on replay: long enough to read as work happening, short enough
# that a 40-second run plays in about ten. Text keeps its natural rhythm.
MAX_TEXT_GAP_S = 0.05
MAX_STEP_GAP_S = 0.9
MAX_OTHER_GAP_S = 0.6


@dataclass(frozen=True)
class Recording:
    question: str
    business_type: str
    model: str
    recorded_on: str
    events: list[dict[str, Any]]   # {"t": seconds since the question, "event": name, "data": {...}}
    path: Path

    def summary(self) -> dict[str, str]:
        return {"question": self.question, "business_type": self.business_type, "recorded_on": self.recorded_on}


def normalise(question: str) -> str:
    """Case, punctuation and spacing don't matter when matching a question to a recording."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", question.lower())).strip()


def slug(question: str) -> str:
    """A plain-ASCII file name: "café" -> "cafe"."""
    ascii_ = unicodedata.normalize("NFKD", normalise(question)).encode("ascii", "ignore").decode()
    return "-".join(ascii_.split())[:80] or "question"


@lru_cache(maxsize=4)
def _load(directory: Path, version: float) -> tuple[Recording, ...]:
    out = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        out.append(Recording(question=raw["question"], business_type=raw.get("business_type", "cafe"),
                             model=raw.get("model", ""), recorded_on=raw.get("recorded_on", ""),
                             events=raw["events"], path=path))
    # The standard questions first, in the order the demo offers them; any others after.
    order = {normalise(q): i for i, q in enumerate(STANDARD_QUESTIONS)}
    return tuple(sorted(out, key=lambda r: (order.get(normalise(r.question), len(order)), r.question)))


def recordings(directory: Path | None = None) -> tuple[Recording, ...]:
    """Every recording on disk (re-read when a file is added or changed)."""
    directory = directory or REPLAY_DIR
    if not directory.exists():
        return ()
    version = max((p.stat().st_mtime for p in directory.glob("*.json")), default=0.0)
    return _load(directory, version)


def find(question: str, business_type: str | None = None, directory: Path | None = None) -> Recording | None:
    key = normalise(question)
    for r in recordings(directory):
        if normalise(r.question) == key and (business_type is None or r.business_type == business_type):
            return r
    return None


def replay(rec: Recording, speed: float = 1.0, sleep=time.sleep) -> Iterator[tuple[str, dict]]:
    """The recorded events, paced like the original with the long waits shortened."""
    last = 0.0
    for ev in rec.events:
        name, data, t = ev["event"], ev["data"], float(ev.get("t", last))
        gap = max(0.0, t - last)
        last = t
        cap = MAX_TEXT_GAP_S if name == "text" else MAX_STEP_GAP_S if name in ("step", "step_done") else MAX_OTHER_GAP_S
        if speed > 0:
            sleep(min(gap, cap) / speed)
        if name == "status":
            data = {**data, "replay": {"recorded_on": rec.recorded_on, "model": rec.model}}
        yield name, data


# --- recording -------------------------------------------------------------------------


def record(question: str, business_type: str = "cafe", directory: Path | None = None) -> Path:
    """Run the analyst for real on an empty workspace and save everything it streams."""
    directory = directory or REPLAY_DIR
    # Imported here: replaying must not need the model client or the API layer.
    from sitescore.analyst import Toolbox, Workspace, run_analyst
    from sitescore.api.deps import get_store
    from sitescore.api.routes_analyst import get_chat_model

    model = get_chat_model()
    if model is None:
        raise SystemExit("Recording needs a live model: set OPENROUTER_API_KEY in .env.")
    toolbox = Toolbox(store=get_store(), workspace=Workspace(business_type=business_type))
    started = time.perf_counter()
    events = []
    for name, data in run_analyst(model, toolbox, [], question):
        events.append({"t": round(time.perf_counter() - started, 3), "event": name,
                       "data": json.loads(json.dumps(data, default=str))})
        if name == "error":
            raise SystemExit(f"The run failed, nothing saved: {data.get('message')}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug(question)}.json"
    path.write_text(json.dumps({
        "question": question, "business_type": business_type, "model": model.name,
        "recorded_on": dt.date.today().isoformat(),  # noqa: DTZ011
        "events": events,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sitescore.analyst.replay", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="run the analyst live and save the run")
    rec.add_argument("questions", nargs="*", help="default: the demo's standard questions")
    rec.add_argument("--business-type", default="cafe")
    sub.add_parser("list", help="show the saved recordings")
    args = parser.parse_args(argv)
    if args.cmd == "list":
        for r in recordings():
            steps = sum(e["event"] == "step" for e in r.events)
            print(f"{r.recorded_on}  {r.business_type:<10} {steps:>2} steps  {r.question}")
        return
    for q in args.questions or STANDARD_QUESTIONS:
        t0 = time.perf_counter()
        path = record(q, args.business_type)
        print(f"saved {path.relative_to(ROOT)} ({time.perf_counter() - t0:.0f} s)")


if __name__ == "__main__":
    main()
