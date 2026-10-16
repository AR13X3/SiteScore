const compact = new Intl.NumberFormat("en-AU", {
  style: "currency",
  currency: "AUD",
  currencyDisplay: "narrowSymbol",
  notation: "compact",
  maximumFractionDigits: 1,
});

const whole = new Intl.NumberFormat("en-AU", {
  style: "currency",
  currency: "AUD",
  currencyDisplay: "narrowSymbol",
  maximumFractionDigits: 0,
});

/** $128K, $4.2M */
export const money = (n: number) => compact.format(n);

/** $128,262 */
export const moneyExact = (n: number) => whole.format(n);

/** 62% */
export const pct = (n: number) => `${Math.round(n * 100)}%`;

/** Readable name for a Monte Carlo parameter path. */
export function parameterLabel(path: string): string {
  const parts = path.split(".");
  const last = parts[parts.length - 1].replace(/_/g, " ");
  const known: Record<string, string> = {
    "avg transaction value": "spend per visit",
    "ramp months to 90pct": "ramp-up speed",
    "ramp start share": "opening awareness",
    beta: "distance decay",
    "distance m": "pull of other options",
    "price elasticity": "price sensitivity",
    "monthly reconsider share": "habit strength",
  };
  const name = known[last] ?? last;
  return parts.includes("segments") ? `${parts[parts.indexOf("segments") + 1]} ${name}` : name;
}

/** +12%, -5% */
export const signedPct = (n: number) => `${n >= 0 ? "+" : "−"}${Math.abs(n * 100).toFixed(0)}%`;

/** "2026-11-01" -> "Nov 26" */
export const shortMonth = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { month: "short", year: "2-digit" });

/** Escape text before it goes into an HTML string (ECharts tooltips). */
export const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/**
 * "CC BY 4.0 (NSW Spatial Services); ODbL 1.0 (Nominatim)" -> two licences, each a short
 * name and its note, so long licence strings wrap as notes instead of one long tag.
 */
export function licenceParts(text: string): { name: string; note: string }[] {
  const items: string[] = [];
  let depth = 0;
  let cur = "";
  for (const ch of text) {
    if (ch === "(") depth++;
    if (ch === ")") depth = Math.max(0, depth - 1);
    if (ch === ";" && depth === 0) {
      items.push(cur);
      cur = "";
    } else cur += ch;
  }
  items.push(cur);
  return items
    .map((it) => it.trim())
    .filter(Boolean)
    .map((it) => {
      const open = it.indexOf("(");
      if (open < 0) return { name: it, note: "" };
      return { name: it.slice(0, open).trim(), note: it.slice(open + 1).replace(/\)\s*$/, "").trim() };
    });
}
