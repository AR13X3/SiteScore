import type { OutcomeComparison } from "./types";

/** Does any rung's gain over foot traffic clear the noise (90% interval above zero)? */
export function ladderVerdict(c: OutcomeComparison): string {
  if (!c.steps.length) return "";
  const winners = c.steps.filter((s) => s.gain_ci && s.gain_ci[0] > 0);
  if (!winners.length) return "No layer adds ranking power over foot traffic that clears the noise: every 90% interval for the gain includes or touches zero.";
  const joined = winners.map((s) => s.label.replace(/^\+ /, "")).join("; ");
  const names = joined.charAt(0).toUpperCase() + joined.slice(1);
  const weak = winners.every((s) => !s.spearman_ci || s.spearman_ci[0] <= 0);
  return `${names}: gain over foot traffic with a 90% interval above zero.` +
    (weak ? " But the correlation itself is weak: its interval still includes zero." : "") +
    " Several outcomes are compared, so one interval clearing zero is a lead, not proof.";
}
