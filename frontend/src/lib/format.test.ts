import assert from "node:assert/strict";
import { test } from "node:test";

import { licenceParts } from "./format.ts";

test("a licence string splits into short names and their notes", () => {
  assert.deepEqual(licenceParts("CC BY 4.0"), [{ name: "CC BY 4.0", note: "" }]);
  assert.deepEqual(licenceParts("CC BY 4.0 (NSW Spatial Services); ODbL 1.0 (Nominatim)"), [
    { name: "CC BY 4.0", note: "NSW Spatial Services" },
    { name: "ODbL 1.0", note: "Nominatim" },
  ]);
  // A semicolon inside the note doesn't split it.
  assert.deepEqual(licenceParts("Google Maps Platform Terms (time-limited caching; place IDs may be stored)"), [
    { name: "Google Maps Platform Terms", note: "time-limited caching; place IDs may be stored" },
  ]);
});
