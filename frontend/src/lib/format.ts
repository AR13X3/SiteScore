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

/** +12%, -5% */
export const signedPct = (n: number) => `${n >= 0 ? "+" : "−"}${Math.abs(n * 100).toFixed(0)}%`;

/** "2026-11-01" -> "Nov 26" */
export const shortMonth = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { month: "short", year: "2-digit" });

/** Escape text before it goes into an HTML string (ECharts tooltips). */
export const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
