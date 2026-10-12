"""The analyst's tools: SiteScore's own model, spot finder, backtest and data, plus UI actions.

Every number the analyst quotes comes from one of these. Each tool returns:

- `result`: a compact JSON-able dict for the model (rounded, no 36-month arrays),
- `summary`: one line for the person watching the analyst work,
- `ui`: an optional action the workspace applies (put sites on the map, show a search,
  open a brief), so the analyst changes what you see, not just what it says.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from sitescore.api import routes_backtest, routes_meta, routes_model, routes_search
from sitescore.backtest import OSM_COHORT
from sitescore.config import Costs, load_business_types, load_model_config, load_region
from sitescore.datastore import DataStore
from sitescore.model.types import Site

MAX_SITES = 5


class ToolError(Exception):
    """A tool couldn't run; the message goes back to the model so it can adjust."""


class Finder(BaseModel):
    lat: float
    lon: float
    radius_m: float


class Workspace(BaseModel):
    """What the person has open in the app: the analyst's defaults and context."""

    business_type: str = "cafe"
    as_of: dt.date | None = None
    costs: Costs | None = None
    sites: list[Site] = Field(default_factory=list, max_length=MAX_SITES)
    selected_id: str | None = None
    finder: Finder | None = None


@dataclass
class ToolOutput:
    result: dict[str, Any]
    summary: str
    ui: dict[str, Any] | None = None


@dataclass
class Toolbox:
    store: DataStore
    workspace: Workspace
    # Per-conversation memory of what the model has already seen, so a brief can pin
    # its recommended site and the UI can label pins consistently.
    seen: dict[str, Any] = field(default_factory=dict)

    # --- dispatch -------------------------------------------------------------------

    def run(self, name: str, args: dict[str, Any]) -> ToolOutput:
        fn: Callable[[dict[str, Any]], ToolOutput] | None = getattr(self, f"tool_{name}", None)
        if fn is None:
            raise ToolError(f"Unknown tool {name!r}.")
        try:
            return fn(args)
        except HTTPException as exc:
            raise ToolError(str(exc.detail)) from exc
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise ToolError(f"Bad arguments for {name}: {exc}") from exc

    # --- helpers --------------------------------------------------------------------

    def _type(self, args: dict) -> str:
        t = args.get("business_type") or self.workspace.business_type
        if t not in load_business_types():
            raise ToolError(f"Unknown business type {t!r}. Known: {', '.join(load_business_types())}.")
        return t

    def _as_of(self, args: dict) -> dt.date | None:
        v = args.get("as_of")
        return dt.date.fromisoformat(v) if v else self.workspace.as_of

    def _costs(self, args: dict, business_type: str) -> Costs | None:
        """Workspace costs (or the profile's), with any per-call overrides on top."""
        base = self.workspace.costs if business_type == self.workspace.business_type else None
        base = base or load_business_types()[business_type].costs
        overrides = {k: args[k] for k in Costs.model_fields if args.get(k) is not None}
        if base is None and not overrides:
            return None
        if base is None:
            raise ToolError("This business type has no cost profile, so cost overrides need all four costs.")
        return base.model_copy(update=overrides)

    @staticmethod
    def _sites(raw: list[dict]) -> list[Site]:
        if not raw:
            raise ToolError("Give at least one site.")
        if len(raw) > MAX_SITES:
            raise ToolError(f"At most {MAX_SITES} sites at a time.")
        return [Site(id=f"site-{i + 1}", label=str(s.get("label") or f"Site {i + 1}")[:80],
                     lat=float(s["lat"]), lon=float(s["lon"])) for i, s in enumerate(raw)]

    # --- model tools ------------------------------------------------------------------

    def tool_geocode(self, args: dict) -> ToolOutput:
        q = str(args.get("query", "")).strip()
        if len(q) < 3:
            raise ToolError("Query too short.")
        hits = routes_meta.geocode(q)[:5]
        if not hits:
            return ToolOutput({"matches": [], "note": "No address found in the region (or offline)."},
                              f"No match for “{q}”")
        return ToolOutput({"matches": [{"label": h["label"], "lat": round(h["lat"], 6),
                                        "lon": round(h["lon"], 6)} for h in hits]},
                          f"Found {hits[0]['label']}")

    def tool_simulate_sites(self, args: dict) -> ToolOutput:
        btype = self._type(args)
        sites = self._sites(args.get("sites") or [])
        costs = self._costs(args, btype)
        req = routes_model.SimulateRequest(business_type=btype, sites=sites, as_of=self._as_of(args),
                                           uncertainty=True, costs=costs)
        r = routes_model.simulate_sites(req, self.store)
        odds = {u.site_id: u for u in (r.uncertainty.sites if r.uncertainty else [])}
        expl = {e.site_id: e for e in r.explanations}
        out = []
        for s in r.sites:
            e, u = expl[s.site.id], odds.get(s.site.id)
            drivers = sorted(e.contributions, key=lambda c: abs(c.pct_effect), reverse=True)[:4]
            out.append({
                "label": s.site.label, "lat": round(s.site.lat, 6), "lon": round(s.site.lon, 6),
                "rank": e.rank,
                "revenue_36m": _r(s.total_revenue),
                "revenue_36m_p10_p90": [_r(u.total_revenue["p10"]), _r(u.total_revenue["p90"])] if u else None,
                "profit_36m": _r(s.total_profit),
                "profit_36m_p10_p90": ([_r(u.total_profit["p10"]), _r(u.total_profit["p90"])]
                                       if u and u.total_profit else None),
                "chance_best": _p(u.prob_best) if u and len(r.sites) > 1 else None,
                "chance_of_36m_loss": _p(u.prob_loss) if u and u.prob_loss is not None else None,
                "mature_monthly_revenue": _r(s.mature.monthly_revenue),
                "mature_monthly_profit": _r(s.mature.monthly_profit),
                "est_rent_monthly": _r(s.mature.rent.monthly) if s.mature.rent else None,
                "vs_average_candidate_pct": round(e.vs_average_pct * 100, 1) if len(r.sites) > 1 else None,
                "headline": e.headline,
                "biggest_drivers_vs_average": [{"layer": c.label, "effect_pct": round(c.pct_effect * 100, 1)}
                                               for c in drivers] if len(r.sites) > 1 else [],
                "layers": {lyr.label: lyr.summary for lyr in [*s.mature.layers, s.dynamics]},
            })
        out.sort(key=lambda x: x["rank"])
        best = out[0]
        summary = (f"{len(out)} site{'s' if len(out) > 1 else ''} simulated over {r.horizon_months} months"
                   + (f" · best: {best['label']}" if len(out) > 1 else f" · ${best['revenue_36m']:,.0f} revenue"))
        self.seen.update({o["label"]: o for o in out})
        return ToolOutput({
            "business_type": btype, "as_of": str(r.as_of), "opens": str(r.open_date),
            "horizon_months": r.horizon_months, "scenarios": r.uncertainty.n_runs if r.uncertainty else 0,
            "costs_used": costs.model_dump() if costs else None,
            "sites": out,
        }, summary)

    def tool_find_spots(self, args: dict) -> ToolOutput:
        btype = self._type(args)
        radius = float(args.get("radius_m") or 1000)
        limit = load_model_config().search.max_radius_m
        radius = max(250.0, min(radius, limit))
        rank_by = args.get("rank_by") or "revenue"
        costs = self._costs(args, btype)
        if rank_by == "profit" and costs is None:
            rank_by = "revenue"
        req = routes_search.SearchRequest(
            business_type=btype, lat=float(args["lat"]), lon=float(args["lon"]), radius_m=radius,
            where=args.get("where") or "anywhere", retail_only=args.get("retail_only", True),
            rank_by=rank_by, as_of=self._as_of(args), costs=costs)
        r = routes_search.search(req, self.store)
        spots = [{
            "letter": chr(64 + sp.rank), "label": sp.label, "kind": sp.kind,
            "former_use": sp.former_use or None, "lat": round(sp.lat, 6), "lon": round(sp.lon, 6),
            "revenue_36m": _r(sp.total_revenue), "profit_36m": _r(sp.total_profit),
            "revenue_36m_p10_p90": [_r(v) for v in sp.revenue_range] if sp.revenue_range else None,
            "chance_of_36m_loss": _p(sp.prob_loss), "est_rent_monthly": _r(sp.rent_monthly),
            "headline": sp.headline,
        } for sp in r.spots]
        summary = (f"Scored {r.n_candidates} candidates in {radius / 1000:.1f} km · "
                   + (f"top: {spots[0]['label']}" if spots else "no spots found"))
        return ToolOutput({
            "business_type": btype, "as_of": str(r.as_of), "ranked_by": r.rank_by, "where": r.where,
            "candidates_scored": r.n_candidates, "shortlisted_full_model": r.n_shortlisted,
            "spots": spots, "notes": r.notes,
        }, summary, ui={"type": "search", "result": r.model_dump(mode="json"),
                        "settings": {"lat": req.lat, "lon": req.lon, "radius": radius, "where": req.where,
                                     "retailOnly": req.retail_only, "rankBy": req.rank_by}})

    def tool_inspect_site(self, args: dict) -> ToolOutput:
        btype = self._type(args)
        site = self._sites([{"label": args.get("label") or "Site", "lat": args["lat"], "lon": args["lon"]}])[0]
        req = routes_model.EvaluateRequest(business_type=btype, sites=[site], as_of=self._as_of(args))
        res = routes_model.evaluate(req, self.store)[0]
        layers = {lyr.key: lyr for lyr in res.layers}
        demand = layers["demand"].details.get("segments", {})
        comp = layers["competition"].details
        fit = layers["fit"].details
        price = layers.get("price")
        return ToolOutput({
            "label": site.label, "business_type": btype, "as_of": str(res.as_of),
            "mature_monthly_revenue": _r(res.monthly_revenue),
            "mature_monthly_profit": _r(res.monthly_profit),
            "monthly_visits": _r(res.monthly_visits),
            "layers": {lyr.label: {"factor": round(lyr.factor, 4), "unit": lyr.unit, "summary": lyr.summary}
                       for lyr in res.layers},
            "catchment": {seg: {"walk_minutes": d.get("walk_minutes"), "people_in_reach": _r(d.get("people_in_reach")),
                                "potential_customers": _r(d.get("potential_customers"))}
                          for seg, d in demand.items()},
            "competition": {k: comp.get(k) for k in ("competitors_within_400m", "competitors_within_800m",
                                                     "nearest_competitor_m", "share_if_alone")}
            | {"top_competitors": [{"name": c["name"], "distance_m": c["distance_m"],
                                     "share_of_local_demand_pct": round(c["share_of_local_demand"] * 100, 1)}
                                    for c in comp.get("top_competitors", [])[:6]]},
            "anchors": [{"name": a["name"], "distance_m": a["distance_m"]}
                        for a in layers["anchors"].details.get("anchors", [])],
            "demographics": [{"feature": f["description"], "z_vs_region": f["catchment_z"], "why": f["why"]}
                             for f in fit.get("features", [])],
            "pricing": ({k: price.details.get(k) for k in ("our_price_before", "suggested_price", "reference_price")}
                        if price else None),
            "rent": res.rent.model_dump() if res.rent else None,
        }, f"{site.label}: ${res.monthly_revenue:,.0f}/month mature revenue",
            ui={"type": "focus", "lat": site.lat, "lon": site.lon, "label": site.label})

    def tool_model_track_record(self, args: dict) -> ToolOutput:
        btype = self._type(args)
        r = routes_backtest.run(routes_backtest.BacktestRequest(cohort=OSM_COHORT, business_type=btype),
                                self.store)
        ladders = []
        for o in r.ladder:
            if not o.available or not o.steps:
                continue
            base, full = o.steps[0], o.steps[-1]
            winners = [s.label for s in o.steps if s.gain_ci and s.gain_ci[0] > 0]
            ladders.append({
                "outcome": o.label, "n": base.n,
                "foot_traffic_only_spearman": _f(base.spearman), "full_model_spearman": _f(full.spearman),
                "full_model_spearman_90ci": [_f(v) for v in full.spearman_ci] if full.spearman_ci else None,
                "layers_whose_gain_clears_noise": winners,
            })
        a, s = r.accuracy, r.survival
        return ToolOutput({
            "what": "Time-safe backtest: each real opening predicted with only data published before it opened.",
            "business_type": btype, "openings_scored": a.n,
            "pairs_ranked_correctly": _f(a.pairwise_accuracy),
            "pairs_ranked_correctly_foot_traffic_only": _f(a.baseline_pairwise_accuracy),
            "survival": {"horizon_months": s.horizon_months, "counts": s.status_counts},
            "outcome_sources": r.outcome_sources, "which_layers_help": ladders,
            "caveats": r.caveats[:4],
        }, f"Backtest: {a.n} real openings scored")

    def tool_data_coverage(self, args: dict) -> ToolOutput:
        tables = routes_meta.data_status(self.store)
        rng = routes_meta.as_of_range(self.store)
        types = routes_meta.business_types()
        real = sum(t["provenance"] == "real" for t in tables if t["model_visible"])
        used = sum(1 for t in tables if t["model_visible"])
        return ToolOutput({
            "region": load_region().name,
            "as_of_range": {"min": str(rng["min"]), "max": str(rng["max"])},
            "business_types": types,
            "tables": [{"table": t["table"], "source": t["source"], "provenance": t["provenance"],
                        "rows": t["rows"], "model_input": t["model_visible"], "note": t["note"] or None}
                       for t in tables],
            "known_gaps": [
                "No open data on commercial rents: rent is an index on a typical-site rent.",
                "No sales data: the backtest scores against Google reviews and survival instead.",
                "Buses are not modelled (only rail, metro and light-rail patronage).",
                "One region so far (City of Parramatta).",
            ],
        }, f"{real} of {used} model inputs are real data")

    # --- UI actions ------------------------------------------------------------------

    def tool_show_on_map(self, args: dict) -> ToolOutput:
        sites = self._sites(args.get("sites") or [])
        mode = "add" if args.get("mode") == "add" else "replace"
        return ToolOutput({"shown": len(sites), "mode": mode,
                           "note": "The workspace now simulates these sites and shows the chart and "
                                   "why-cards below the map."},
                          f"Put {len(sites)} site{'s' if len(sites) > 1 else ''} on the map",
                          ui={"type": "set_sites", "mode": mode,
                              "sites": [{"label": s.label, "lat": s.lat, "lon": s.lon} for s in sites]})

    def tool_write_brief(self, args: dict) -> ToolOutput:
        brief = {
            "title": str(args.get("title") or "Site brief")[:120],
            "verdict": str(args.get("verdict") or ""),
            "recommended": args.get("recommended") or None,
            "key_numbers": [{"label": str(k.get("label", "")), "value": str(k.get("value", ""))}
                            for k in (args.get("key_numbers") or [])][:8],
            "reasons": [str(x) for x in (args.get("reasons") or [])][:6],
            "risks": [str(x) for x in (args.get("risks") or [])][:6],
            "next_steps": [str(x) for x in (args.get("next_steps") or [])][:6],
            "business_type": self.workspace.business_type,
            "as_of": str(self.workspace.as_of or dt.date.today()),  # noqa: DTZ011
        }
        if not brief["verdict"]:
            raise ToolError("A brief needs a verdict.")
        return ToolOutput({"published": True}, f"Wrote “{brief['title']}”", ui={"type": "brief", "brief": brief})


def _r(v: float | None) -> float | None:
    return None if v is None else round(float(v))


def _p(v: float | None) -> float | None:
    return None if v is None else round(float(v) * 100, 1)


def _f(v: float | None) -> float | None:
    return None if v is None else round(float(v), 3)


# --- Schemas (OpenAI function-calling format, which OpenRouter passes to every model) ---

_SITE = {"type": "object", "properties": {
    "label": {"type": "string", "description": "Short human name, e.g. 'Church St north'"},
    "lat": {"type": "number"}, "lon": {"type": "number"}}, "required": ["label", "lat", "lon"]}
_BTYPE = {"type": "string", "description": "Business type id (default: the one open in the app)"}
_AS_OF = {"type": "string", "description": "Run as of this past date (YYYY-MM-DD) using only data "
                                           "published by then. Omit for today."}
_COSTS = {
    "rent_per_month": {"type": "number", "description": "Rent of a TYPICAL site, $/month; each site's "
                                                        "own rent is estimated from it"},
    "wages_per_month": {"type": "number"},
    "cogs_share": {"type": "number", "description": "Cost of goods as a share of revenue, 0-0.9"},
    "other_fixed_per_month": {"type": "number"},
}


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required or []}}}


TOOL_SPECS: list[dict] = [
    _fn("geocode", "Find coordinates for an address, street, landmark or suburb in the region.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("find_spots",
        "Search a circle for the best places to open: scores every candidate (grid along shopping "
        "strips, or vacant shopfronts), re-runs the best with the full model and returns the top 5 "
        "with 36-month revenue/profit, ranges, rent and chance of loss. Also shows the search on the "
        "user's map. Takes 3-10 s.",
        {"lat": {"type": "number"}, "lon": {"type": "number"},
         "radius_m": {"type": "number", "description": "250-3000, default 1000"},
         "where": {"type": "string", "enum": ["anywhere", "vacant"],
                   "description": "'vacant' = only empty shopfronts mapped on OpenStreetMap"},
         "rank_by": {"type": "string", "enum": ["revenue", "profit"]},
         "retail_only": {"type": "boolean", "description": "Grid only near existing similar businesses (default true)"},
         "business_type": _BTYPE, "as_of": _AS_OF, **_COSTS},
        ["lat", "lon"]),
    _fn("simulate_sites",
        "Simulate 1-5 candidate sites over 36 months with 300 Monte Carlo scenarios: revenue, profit "
        "with each site's estimated rent, P10-P90 ranges, chance each is best, chance of a 36-month "
        "loss, and per-layer reasons. Pass cost fields to test what-if scenarios.",
        {"sites": {"type": "array", "items": _SITE, "minItems": 1, "maxItems": 5},
         "business_type": _BTYPE, "as_of": _AS_OF, **_COSTS},
        ["sites"]),
    _fn("inspect_site",
        "Deep look at one location: walking catchments by customer type, nearby competitors and the "
        "share of demand each takes, anchors, demographic fit, pricing, rent estimate.",
        {"lat": {"type": "number"}, "lon": {"type": "number"}, "label": {"type": "string"},
         "business_type": _BTYPE, "as_of": _AS_OF},
        ["lat", "lon"]),
    _fn("model_track_record",
        "How well SiteScore predicted real openings in the time-safe backtest (and which layers add "
        "accuracy over foot traffic alone). Use when asked how much to trust the model. Can take "
        "~30 s the first time.",
        {"business_type": _BTYPE}),
    _fn("data_coverage",
        "Which data sources feed the model, real or mock, how fresh, and the known gaps.", {}),
    _fn("show_on_map",
        "Put sites on the user's map as the comparison set. The app then draws their 36-month chart "
        "and why-cards. Use for your final shortlist (max 5).",
        {"sites": {"type": "array", "items": _SITE, "minItems": 1, "maxItems": 5},
         "mode": {"type": "string", "enum": ["replace", "add"], "description": "default replace"}},
        ["sites"]),
    _fn("write_brief",
        "Publish a decision brief card the user can download: use at the end of a recommendation. "
        "Every number must come from a tool result in this conversation.",
        {"title": {"type": "string"},
         "verdict": {"type": "string", "description": "2-3 sentence bottom line"},
         "recommended": _SITE,
         "key_numbers": {"type": "array", "items": {"type": "object", "properties": {
             "label": {"type": "string"}, "value": {"type": "string"}}, "required": ["label", "value"]}},
         "reasons": {"type": "array", "items": {"type": "string"}},
         "risks": {"type": "array", "items": {"type": "string"}},
         "next_steps": {"type": "array", "items": {"type": "string"},
                        "description": "What to verify on the ground before signing a lease"}},
        ["title", "verdict"]),
]


def step_label(name: str, args: dict) -> str:
    """What the analyst is doing, in words, while a tool runs."""
    n = len(args.get("sites") or [])
    radius = float(args.get("radius_m") or 1000)
    return {
        "geocode": f"Looking up “{args.get('query', '')}”",
        "find_spots": (f"Scanning {radius / 1000:.1f} km for "
                       + ("vacant shopfronts" if args.get("where") == "vacant" else "the best spots")
                       + (" by profit" if args.get("rank_by") == "profit" else "")),
        "simulate_sites": f"Simulating {n} site{'s' if n != 1 else ''} × 300 scenarios over 36 months",
        "inspect_site": f"Inspecting the catchment at {args.get('label') or 'this spot'}",
        "model_track_record": "Checking the model's backtest record",
        "data_coverage": "Checking data coverage",
        "show_on_map": f"Putting {n} site{'s' if n != 1 else ''} on the map",
        "write_brief": "Writing the decision brief",
    }.get(name, name)
