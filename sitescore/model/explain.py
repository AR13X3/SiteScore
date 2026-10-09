"""Why each site wins or loses: exact per-layer attribution across candidates.

Each site's horizon revenue is a product of layer factors:

    total = horizon x demand x fit x anchors x share x behaviour x price
            x spend x capacity x time

Compare every factor with the average candidate (geometric mean across sites).
In logs the differences add up exactly to log(total / average total), so the
"why" always reconciles to the revenue gap. For display, each log difference
becomes a % effect and a dollar step in a waterfall from the average candidate
to this site.
"""

from __future__ import annotations

import math

from sitescore.model.types import Contribution, SiteExplanation, SiteSimulation

ORDER = ["demand", "fit", "anchors", "competition", "behaviour", "price", "spend", "capacity",
         "time"]
LABELS = {
    "demand": "Demand", "fit": "Demographic fit", "anchors": "Anchors",
    "competition": "Competition", "behaviour": "Customer behaviour", "price": "Price response",
    "spend": "Spend per customer", "capacity": "Capacity",
    "time": "Ramp-up, seasons & growth",
}
PHRASES = {  # (when it helps, when it hurts)
    "demand": ("more potential customers within walking distance",
               "fewer potential customers within walking distance"),
    "fit": ("locals who better match the customer profile", "locals who match the profile less well"),
    "anchors": ("more foot traffic from anchor tenants", "less foot traffic from anchor tenants"),
    "competition": ("less competition for its customers", "tougher competition nearby"),
    "behaviour": ("customers' tastes favouring it", "customers' tastes favouring rivals"),
    "price": ("milder price cuts by rivals", "rivals cutting prices in response"),
    "spend": ("customers who visit more often", "customers who visit less often"),
    "capacity": ("", "hitting its capacity limit"),
    "time": ("faster growth from new developments and seasons",
             "slower growth over the period"),
}


def factors(sim: SiteSimulation) -> dict[str, float]:
    f = {layer.key: layer.factor for layer in sim.mature.layers}
    f["time"] = sim.dynamics.factor
    return {k: f.get(k, 1.0) for k in ORDER}


def explain(sims: list[SiteSimulation]) -> tuple[list[SiteExplanation], float]:
    """Explanations ranked best first, plus the baseline (average candidate) total."""
    ranked = sorted(sims, key=lambda s: -s.total_revenue)
    valid = [s for s in sims if s.total_revenue > 0 and all(v > 0 for v in factors(s).values())]
    if not valid:
        return [_no_demand(s, i + 1) for i, s in enumerate(ranked)], 0.0

    logs = {s.site.id: {k: math.log(v) for k, v in factors(s).items()} for s in valid}
    mean_log = {k: sum(v[k] for v in logs.values()) / len(valid) for k in ORDER}
    baseline = math.exp(sum(math.log(s.total_revenue) for s in valid) / len(valid))

    out = []
    for rank, s in enumerate(ranked, start=1):
        if s.site.id not in logs:
            out.append(_no_demand(s, rank))
            continue
        running, contributions = baseline, []
        for k in ORDER:
            diff = logs[s.site.id][k] - mean_log[k]
            step = running * (math.exp(diff) - 1)
            running += step
            contributions.append(Contribution(key=k, label=LABELS[k], ratio=math.exp(diff),
                                              pct_effect=math.exp(diff) - 1, dollars=step))
        out.append(SiteExplanation(
            site_id=s.site.id, rank=rank, total_revenue=s.total_revenue,
            vs_average_pct=s.total_revenue / baseline - 1,
            headline=_headline(s, rank, len(valid), s.total_revenue / baseline - 1, contributions),
            contributions=contributions,
        ))
    return out, baseline


def _headline(s: SiteSimulation, rank: int, n_valid: int, vs_avg: float,
              contributions: list[Contribution]) -> str:
    name = s.site.label or s.site.id
    if n_valid == 1:
        return f"{name}: add another site to compare"
    meaningful = [c for c in contributions if abs(c.pct_effect) >= 0.03]
    helps = sorted((c for c in meaningful if c.pct_effect > 0), key=lambda c: -c.pct_effect)
    hurts = sorted((c for c in meaningful if c.pct_effect < 0), key=lambda c: c.pct_effect)
    lead = f"{name} ranks #{rank}, {vs_avg:+.0%} vs the average candidate"
    reasons = []
    if helps:
        reasons.append(f"helped by {PHRASES[helps[0].key][0]} ({helps[0].pct_effect:+.0%})")
    if hurts:
        reasons.append(f"held back by {PHRASES[hurts[0].key][1]} ({hurts[0].pct_effect:+.0%})")
    return lead + (": " + "; ".join(reasons) if reasons else "")


def _no_demand(s: SiteSimulation, rank: int) -> SiteExplanation:
    return SiteExplanation(
        site_id=s.site.id, rank=rank, total_revenue=s.total_revenue, vs_average_pct=-1.0,
        headline=f"{s.site.label or s.site.id}: no customers within walking distance",
        contributions=[],
    )
