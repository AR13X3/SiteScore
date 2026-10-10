// Run with `npm test` (Node's built-in runner; Node 22.6+ strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { bulkAdd } from "./finder.ts";

const spots = ["a", "b", "c", "d", "e"];

test("an empty comparison takes the top 3", () => {
  assert.deepEqual(bulkAdd(spots, new Set(), 5, 5), { count: 3, label: "Compare the top 3", note: null });
});

test("with 4 sites already, only one fits: no bulk button, and a note says why", () => {
  const b = bulkAdd(spots, new Set(), 1, 5);
  assert.equal(b.count, 0);
  assert.equal(b.note, "Room for 1 more: the comparison holds 5 sites.");
});

test("with room for 2, the button says 2", () => {
  const b = bulkAdd(spots, new Set(), 2, 5);
  assert.equal(b.count, 2);
  assert.equal(b.label, "Compare the top 2");
});

test("after adding A, the next ones are offered", () => {
  assert.equal(bulkAdd(spots, new Set(["a"]), 4, 5).label, "Compare the next 3");
});

test("a full comparison says so", () => {
  assert.match(bulkAdd(spots, new Set(), 0, 5).note ?? "", /full/);
});
