import assert from "node:assert/strict";
import { test } from "node:test";

import { ladderVerdict } from "./ladder.ts";

const step = (key: string, label: string, spearman: number, ci: [number, number], gain: [number, number] | null) =>
  ({ key, label, n: 143, pairs: 100, pairwise_accuracy: 0.6, spearman, spearman_ci: ci, gain_ci: gain });

test("no gain clear of zero", () => {
  const c = { outcome: "x", label: "x", available: true, note: "", steps: [
    step("demand", "Foot traffic only", 0.1, [-0.1, 0.3], null),
    step("competition", "+ competition (Huff)", 0.2, [0.0, 0.4], [-0.05, 0.3]),
  ] };
  assert.match(ladderVerdict(c), /^No layer/);
});

test("a gain clear of zero on a weak correlation is called a lead", () => {
  const c = { outcome: "google_open", label: "x", available: true, note: "", steps: [
    step("demand", "Foot traffic only", -0.08, [-0.24, 0.09], null),
    step("competition", "+ competition (Huff)", 0.12, [-0.01, 0.24], [0.10, 0.29]),
  ] };
  const v = ladderVerdict(c);
  assert.match(v, /^Competition \(Huff\): gain/);
  assert.match(v, /still includes zero/);
  assert.match(v, /a lead, not proof/);
});
