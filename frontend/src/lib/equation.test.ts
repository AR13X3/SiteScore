import assert from "node:assert/strict";
import { test } from "node:test";

import { equationTerms, runningLabel } from "./equation.ts";

const layer = (key: string, factor: number, unit: string) =>
  ({ key, label: key, factor, unit, summary: `${key} summary`, details: {} });

const layers = [
  layer("demand", 13740, "customers"),
  layer("fit", 1.05, "x"),
  layer("anchors", 1.08, "x"),
  layer("competition", 0.017, "share"),
  layer("behaviour", 1.28, "x"),
  layer("price", 1.0, "x"),
  layer("spend", 116.12, "$/customer"),
];
const mature = layers.reduce((a, l) => a * l.factor, 1);
const sim = {
  site: { id: "a", label: "a", lat: 0, lon: 0 },
  mature: { layers, monthly_revenue: mature },
  months: Array.from({ length: 36 }, () => ({})),
  total_revenue: mature * 36 * 0.89,
  total_profit: null,
  dynamics: layer("time", 0.89, "x"),
} as never;

test("the terms multiply out to the forecast", () => {
  const terms = equationTerms(sim);
  assert.deepEqual(terms.map((t) => t.key), [...layers.map((l) => l.key), "months", "time"]);
  const month = terms.find((t) => t.key === "spend")!;
  assert.ok(Math.abs(month.after - mature) < 1e-6);
  assert.ok(month.subtotal && terms[terms.length - 1].subtotal);
  assert.ok(Math.abs(terms[terms.length - 1].after - mature * 36 * 0.89) < 1e-6);
});

test("units follow the chain: people, then customers, then dollars", () => {
  const unit = Object.fromEntries(equationTerms(sim).map((t) => [t.key, t.unit]));
  assert.equal(unit.anchors, "people");
  assert.equal(unit.competition, "customers");
  assert.equal(unit.spend, "month");
  assert.equal(unit.time, "total");
});

test("factors are written the way people read them", () => {
  const shown = Object.fromEntries(equationTerms(sim).map((t) => [t.key, t.shown]));
  assert.equal(shown.demand, "13,740");
  assert.equal(shown.fit, "1.05");
  assert.equal(shown.competition, "1.7%");
  assert.equal(shown.spend, "$116");
  assert.equal(shown.months, "36");
  assert.equal(runningLabel(266.4, "customers", String), "266 customers");
});
