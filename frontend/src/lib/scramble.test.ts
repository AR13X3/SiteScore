import assert from "node:assert/strict";
import { test } from "node:test";

import { scrambleFrame } from "./scramble.ts";

const zero = () => 0; // always the first glyph, "a"

test("starts blank-ish and ends exact", () => {
  assert.equal(scrambleFrame("model.explain()", 1), "model.explain()");
  const start = scrambleFrame("model.explain()", 0, zero);
  assert.equal(start.length, "model.explain()".length);
  assert.match(start, /^a{4} +$/);
});

test("settled characters are final, spaces are kept", () => {
  const f = scrambleFrame("how it works", 0.5, zero);
  assert.equal(f.slice(0, 6), "how it");
  assert.equal(f[3], " ");
  assert.equal(f.length, 12);
});

test("count-up keeps the shape of the text", async () => {
  const { countFrame } = await import("./scramble.ts");
  assert.equal(countFrame("0 of 25", 1), "0 of 25");
  assert.equal(countFrame("0 of 25", 0), "0 of 0");
  assert.equal(countFrame("60%", 0), "0%");
  assert.equal(countFrame("0.70", 1), "0.70");
  assert.equal(countFrame("86,700 rows", 1), "86,700 rows");
  assert.equal(countFrame("n/a", 0.5), "n/a");
});
