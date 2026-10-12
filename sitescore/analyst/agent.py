"""The analyst loop: the model plans, calls SiteScore's tools, reads results, and answers.

`run_analyst` yields events for the browser:

    status       {model}
    text         {delta}                          streamed answer text
    step         {id, name, label, args}          a tool started
    step_done    {id, name, ok, summary, ms}      ... and finished
    ui           {type, ...}                      an action for the workspace (map, brief)
    error        {message}
    done         {steps}
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Iterator
from typing import Any

from sitescore.analyst.llm import ChatModel, LLMError, Turn
from sitescore.analyst.tools import TOOL_SPECS, Toolbox, ToolError, step_label
from sitescore.config import load_business_types, load_region

log = logging.getLogger(__name__)

MAX_ROUNDS = 10            # model turns per question (each may call several tools)
MAX_HISTORY = 16           # earlier user/assistant messages kept for follow-ups
MAX_TOOL_RESULT_CHARS = 14_000

Event = tuple[str, dict[str, Any]]


def system_prompt(toolbox: Toolbox) -> str:
    ws = toolbox.workspace
    region = load_region()
    types = ", ".join(f"{p.id} ({p.name}{', draft' if p.status == 'draft' else ''})"
                      for p in load_business_types().values())
    sites = "; ".join(f"{s.label or s.id} at ({s.lat:.5f}, {s.lon:.5f})" for s in ws.sites) or "none yet"
    selected = next((s.label for s in ws.sites if s.id == ws.selected_id), None)
    costs = ws.costs.model_dump() if ws.costs else "the business profile's defaults"
    finder = (f"centred ({ws.finder.lat:.5f}, {ws.finder.lon:.5f}), radius {ws.finder.radius_m:.0f} m"
              if ws.finder else "none")
    today = dt.date.today()  # noqa: DTZ011
    return f"""You are SiteScore's location analyst. You help people decide where to open a business by \
running SiteScore's own simulation model through tools, then explaining what it found. You are \
working inside the SiteScore app, next to a map the person can see.

## What SiteScore is
An open-source location-revenue simulator. Region: {region.name}, {region.state}, Australia. \
Business types: {types}. For a site it multiplies layers: potential customers in walking reach \
(residents, workers, commuters from ABS Census + station patronage) × demographic fit × anchor \
boost × competition share (Huff gravity model) × customer-agent behaviour × competitors' price \
response × $ per customer, then projects 36 months with ramp-up, seasonality and approved \
developments, with 300 Monte Carlo scenarios for P10-P90 ranges. Rent per site is an \
estimate (an index on a typical-site rent from foot traffic and local residential rents), not a \
listing price. Data is official/open (ABS, Transport for NSW, OpenStreetMap, NSW Planning Portal).

## How far to trust it (say so when it matters)
The time-safe backtest on ~29 real café openings found the model points the right way on Google \
reviews but the gain over plain foot traffic is not statistically clear. Treat outputs as a \
structured, explainable comparison of sites, not a revenue guarantee. Use model_track_record if \
the person asks about accuracy.

## The person's workspace right now
- Business type: {ws.business_type}
- Data as of: {ws.as_of or f'today ({today})'}
- Running costs: {costs}
- Sites on the map: {sites}{f' (selected: {selected})' if selected else ''}
- Spot-finder circle: {finder}

## How to work
- Act, don't ask: if a request is reasonably clear, run the tools. Ask only if it is truly ambiguous.
- Every number you state must come from a tool result in this conversation. Never invent figures, \
coordinates, rents or competitor names. If a tool can't answer it, say what's missing.
- Place names → geocode first. "Near X" → find_spots around X (default radius 800-1200 m). \
"Best spot", "where should I open" → find_spots, then simulate_sites on 2-5 finalists (add the \
person's own sites when relevant), then show_on_map with your shortlist, then write_brief.
- What-ifs (higher rent, different wages, opening in the past) → simulate_sites with cost fields \
or as_of. A cheaper but quieter site can win on profit: check profit and chance of loss, not just \
revenue.
- "Why does X win/lose" → use the per-layer drivers; inspect_site for competitors, anchors, \
demographics.
- Vacant shopfronts are leads from OpenStreetMap mappers, not listings: say they need checking.
- Keep answers tight: lead with the answer, then a short markdown list or table of the numbers \
that matter (36-month revenue/profit, P10-P90, chance of loss, est. rent), then 1-2 caveats. Use \
$ with k/M (e.g. $1.2M, $9.8k/month). No long preambles. Don't narrate tool calls; the person \
sees them as they run.
- Today is {today}."""


def run_analyst(model: ChatModel, toolbox: Toolbox, history: list[dict], question: str) -> Iterator[Event]:
    messages: list[dict] = [{"role": "system", "content": system_prompt(toolbox)}]
    messages += [m for m in _clean_history(history)]
    messages.append({"role": "user", "content": question})
    yield "status", {"model": model.name}

    steps = 0
    for _ in range(MAX_ROUNDS):
        turn: Turn | None = None
        try:
            for item in model.stream(messages, TOOL_SPECS):
                if isinstance(item, Turn):
                    turn = item
                else:
                    yield "text", {"delta": item}
        except LLMError as exc:
            yield "error", {"message": str(exc)}
            return
        if turn is None:
            yield "error", {"message": "The model returned nothing."}
            return
        if not turn.tool_calls:
            yield "done", {"steps": steps}
            return

        messages.append({
            "role": "assistant", "content": turn.text or None,
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments or "{}"}}
                           for c in turn.tool_calls],
        })
        if turn.text:
            yield "text", {"delta": "\n\n"}
        for call in turn.tool_calls:
            args = call.args()
            steps += 1
            yield "step", {"id": call.id, "name": call.name, "label": step_label(call.name, args), "args": args}
            started = time.perf_counter()
            try:
                out = toolbox.run(call.name, args)
                content = json.dumps(out.result, default=str)
                ok, summary = True, out.summary
                if out.ui:
                    yield "ui", out.ui
            except ToolError as exc:
                content = json.dumps({"error": str(exc)})
                ok, summary = False, str(exc)
            except Exception as exc:  # a model bug must not kill the conversation
                log.exception("analyst tool %s failed", call.name)
                content = json.dumps({"error": f"Internal error: {exc}"})
                ok, summary = False, f"Failed: {exc}"
            ms = round((time.perf_counter() - started) * 1000)
            yield "step_done", {"id": call.id, "name": call.name, "ok": ok, "summary": summary, "ms": ms}
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": content[:MAX_TOOL_RESULT_CHARS]})

    yield "text", {"delta": "\n\n_I hit my step limit for one question. Ask me to continue._"}
    yield "done", {"steps": steps}


def _clean_history(history: list[dict]) -> list[dict]:
    """Only plain user/assistant text from earlier turns: tool internals aren't replayed."""
    out = [{"role": m["role"], "content": str(m["content"])[:8000]}
           for m in history
           if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    return out[-MAX_HISTORY:]
