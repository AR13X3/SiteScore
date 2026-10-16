import assert from "node:assert/strict";
import { test } from "node:test";

import { type Heatmap, heatIndex, topShare } from "./heat.ts";

// A 10 x 10 square grid, 250 m apart, values 0..99 from south-west to north-east.
const SPACING = 250;
const LAT0 = -33.85;
const LON0 = 150.95;
const dLat = SPACING / 110_574;
const dLon = SPACING / (111_320 * Math.cos((LAT0 * Math.PI) / 180));
const heat: Heatmap = { business_type: "cafe", as_of: "2026-10-16", spacing_m: SPACING, lat: [], lon: [], value: [] };
for (let r = 0; r < 10; r++) {
  for (let c = 0; c < 10; c++) {
    heat.lat.push(LAT0 + r * dLat);
    heat.lon.push(LON0 + c * dLon);
    heat.value.push(r * 10 + c);
  }
}
const idx = heatIndex(heat);

test("nearest finds the cell under a point and nothing far away", () => {
  assert.equal(idx.nearest(LAT0 + 3 * dLat + dLat * 0.2, LON0 + 7 * dLon - dLon * 0.3), 37);
  assert.equal(idx.nearest(LAT0 - 5 * dLat, LON0), -1);
});

test("bins put the hotspots in the top step", () => {
  assert.equal(idx.bin(0), 0);
  assert.equal(idx.bin(99), 4);
  assert.deepEqual(idx.cuts, [40, 65, 82, 93]);
});

test("percentile and its wording", () => {
  assert.equal(idx.percentile(92), 0.92);
  assert.equal(topShare(idx.percentile(92)), "Top 8%");
  assert.equal(topShare(0.3), "Bottom 31%");
  assert.equal(topShare(1), "Top 1%");
});
