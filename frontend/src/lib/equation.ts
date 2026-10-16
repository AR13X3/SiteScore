// A site's forecast written out as the product it is: people x fit x anchors x share x
// ... x spend = a mature month; x months x ramp-up & seasons = 36 months.
import type { Layer, SiteSimulation } from "./types";

export type RunningUnit = "people" | "customers" | "month" | "total";

export interface Term {
  key: string;
  name: string;
  /** What the factor is, under the number: "people", "fit", "share won". */
  caption: string;
  /** The factor as written in the equation: "13,740", "1.05", "1.7%", "$116". */
  shown: string;
  /** What the model says about this layer for this site. */
  summary: string;
  /** Running value before and after this term, and what it counts. */
  before: number | null;
  after: number;
  unit: RunningUnit;
  /** A subtotal sits after this term ("= $39.3K a month"). */
  subtotal: boolean;
}

const CAPTIONS: Record<string, [string, string]> = {
  demand: ["Demand", "people in reach"],
  fit: ["Demographic fit", "fit"],
  anchors: ["Anchors", "anchors"],
  competition: ["Competition", "share won"],
  behaviour: ["Customer agents", "behaviour"],
  price: ["Price response", "prices"],
  spend: ["Spend", "per customer"],
  capacity: ["Capacity", "capacity"],
};

const int = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 });
const dollars = new Intl.NumberFormat("en-AU", {
  style: "currency", currency: "AUD", currencyDisplay: "narrowSymbol", maximumFractionDigits: 0,
});

function shown(l: Layer): string {
  if (l.unit === "share") return `${(l.factor * 100).toFixed(l.factor < 0.1 ? 1 : 0)}%`;
  if (l.unit.startsWith("$")) return dollars.format(l.factor);
  if (l.unit === "x") return l.factor.toFixed(2);
  return int.format(l.factor);
}

export function equationTerms(sim: SiteSimulation): Term[] {
  const terms: Term[] = [];
  let value: number | null = null;
  let unit: RunningUnit = "people";
  for (const l of sim.mature.layers) {
    const before = value;
    value = value === null ? l.factor : value * l.factor;
    if (l.unit === "share") unit = "customers";
    if (l.unit.startsWith("$")) unit = "month";
    const [name, caption] = CAPTIONS[l.key] ?? [l.label, l.unit === "x" ? "factor" : l.unit];
    terms.push({ key: l.key, name, caption, shown: shown(l), summary: l.summary, before, after: value, unit, subtotal: false });
  }
  if (terms.length) terms[terms.length - 1].subtotal = true;
  const months = sim.months.length;
  const mature = value ?? 0;
  terms.push({
    key: "months", name: "Horizon", caption: "months", shown: String(months),
    summary: `The forecast runs ${months} months from opening, month by month.`,
    before: mature, after: mature * months, unit: "total", subtotal: false,
  });
  terms.push({
    key: "time", name: "Ramp-up & seasons", caption: "ramp & seasons", shown: sim.dynamics.factor.toFixed(2),
    summary: sim.dynamics.summary, before: mature * months, after: sim.total_revenue, unit: "total", subtotal: true,
  });
  return terms;
}

/** "13,740 people", "266 customers", "$39.3K a month" (money formatting passed in). */
export function runningLabel(v: number, unit: RunningUnit, money: (n: number) => string): string {
  if (unit === "people") return `${int.format(v)} people`;
  if (unit === "customers") return `${int.format(v)} customers`;
  if (unit === "month") return `${money(v)} a month`;
  return `${money(v)} over the horizon`;
}
