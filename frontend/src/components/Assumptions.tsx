import { parameterLabel } from "../lib/format";
import type { ParameterRange } from "../lib/types";

type Unit = "money" | "pct" | "num" | "metres" | "months";
type Group = "spend" | "choice" | "timing" | "other";

// What each Monte Carlo parameter is, in words, and how to write its value.
const KNOWN: Record<string, { group: Group; label: string; unit: Unit }> = {
  "profile.spend.avg_transaction_value": { group: "spend", label: "Spend per visit", unit: "money" },
  "profile.pricing.price_elasticity": { group: "spend", label: "Price sensitivity", unit: "num" },
  "model.huff.beta": { group: "choice", label: "Distance decay", unit: "num" },
  "model.huff.outside_option.distance_m": { group: "choice", label: "Pull of other options", unit: "metres" },
  "model.abm.monthly_reconsider_share": { group: "choice", label: "Reconsider each month", unit: "pct" },
  "profile.dynamics.ramp_months_to_90pct": { group: "timing", label: "Months to 90% of mature", unit: "months" },
};
const GROUPS: { id: Group; title: string }[] = [
  { id: "spend", title: "spend/" },
  { id: "choice", title: "choice/" },
  { id: "timing", title: "timing/" },
  { id: "other", title: "other/" },
];
const SEGMENT = /^profile\.segments\.(\w+)\.(participation|visits_per_month)$/;

function fmt(v: number, unit: Unit): string {
  if (unit === "money") return `$${v.toFixed(2)}`;
  if (unit === "pct") return `${Math.round(v * 100)}%`;
  if (unit === "metres") return `${Math.round(v)} m`;
  if (unit === "months") return v.toFixed(v < 10 ? 1 : 0);
  return Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
}

/** P10–P90 as a whisker around the base value, on one relative scale shared by every row. */
function Whisker({ p, span }: { p: ParameterRange; span: number }) {
  const x = (v: number) => 50 + ((v / p.base - 1) / span) * 50;
  return (
    <span className="whisker" aria-hidden>
      <i className="whisker__axis" />
      <i className="whisker__range" style={{ left: `${x(p.p10)}%`, width: `${x(p.p90) - x(p.p10)}%` }} />
      <i className="whisker__dot" />
    </span>
  );
}

function Value({ p, unit }: { p: ParameterRange; unit: Unit }) {
  return (
    <span className="assume__value num">
      <strong>{fmt(p.base, unit)}</strong>
      <span className="muted">
        {fmt(p.p10, unit)}–{fmt(p.p90, unit)}
      </span>
    </span>
  );
}

/**
 * What varies across the scenarios, grouped: who comes (a segment table), what they
 * spend, how they choose, and how fast the site ramps up. Each range is drawn against
 * its base value on one shared scale, so the most uncertain assumption stands out.
 */
export function Assumptions({ parameters, runs }: { parameters: ParameterRange[]; runs: number }) {
  const span = Math.max(0.1, ...parameters.flatMap((p) => [Math.abs(p.p10 / p.base - 1), Math.abs(p.p90 / p.base - 1)]));
  const segments = new Map<string, { participation?: ParameterRange; visits?: ParameterRange }>();
  const grouped = new Map<Group, { p: ParameterRange; label: string; unit: Unit }[]>();
  for (const p of parameters) {
    const m = p.path.match(SEGMENT);
    if (m) {
      const row = segments.get(m[1]) ?? {};
      if (m[2] === "participation") row.participation = p;
      else row.visits = p;
      segments.set(m[1], row);
      continue;
    }
    const k = KNOWN[p.path] ?? { group: "other" as Group, label: parameterLabel(p.path), unit: "num" as Unit };
    grouped.set(k.group, [...(grouped.get(k.group) ?? []), { p, label: k.label, unit: k.unit }]);
  }

  return (
    <details className="assumptions">
      <summary>
        <span className="mono assumptions__code">scenario.inputs/</span>
        <span className="assumptions__title">What varies across the {runs} scenarios</span>
        <span className="muted small assumptions__legend">
          <span className="whisker whisker--key" aria-hidden>
            <i className="whisker__axis" />
            <i className="whisker__range" style={{ left: "30%", width: "40%" }} />
            <i className="whisker__dot" />
          </span>
          base value, P10–P90
        </span>
      </summary>
      <div className="assume">
        {segments.size > 0 && (
          <section className="assume__group assume__group--wide">
            <h4 className="mono">who_comes/</h4>
            <table className="assume__matrix">
              <thead>
                <tr>
                  <th scope="col">Customers</th>
                  <th scope="col">Share who'd come</th>
                  <th scope="col">Visits a month</th>
                </tr>
              </thead>
              <tbody>
                {[...segments].map(([name, row]) => (
                  <tr key={name}>
                    <th scope="row">{name[0].toUpperCase() + name.slice(1)}</th>
                    {[row.participation, row.visits].map((p, i) => (
                      <td key={i}>
                        {p ? (
                          <span className="assume__cell">
                            <Value p={p} unit={i === 0 ? "pct" : "num"} />
                            <Whisker p={p} span={span} />
                          </span>
                        ) : (
                          "–"
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
        {GROUPS.filter((g) => grouped.has(g.id)).map((g) => (
          <section key={g.id} className="assume__group">
            <h4 className="mono">{g.title}</h4>
            <ul className="assume__list">
              {grouped.get(g.id)!.map(({ p, label, unit }) => (
                <li key={p.path}>
                  <span className="assume__label">{label}</span>
                  <Value p={p} unit={unit} />
                  <Whisker p={p} span={span} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}
