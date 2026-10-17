import assert from "node:assert/strict";
import { test } from "node:test";

import { countEndpoint, pagePath } from "./analytics.ts";

test("the setting is a GoatCounter code or a full https count URL", () => {
  assert.equal(countEndpoint("joy"), "https://joy.goatcounter.com/count");
  assert.equal(countEndpoint(" Joy-Site "), "https://joy-site.goatcounter.com/count");
  assert.equal(countEndpoint("https://stats.example.com/count"), "https://stats.example.com/count");
});

test("no setting, or a bad one, leaves counting off", () => {
  assert.equal(countEndpoint(undefined), null);
  assert.equal(countEndpoint(""), null);
  assert.equal(countEndpoint("   "), null);
  assert.equal(countEndpoint("http://stats.example.com/count"), null); // not https
  assert.equal(countEndpoint("joy.goatcounter"), null);
  assert.equal(countEndpoint("javascript:alert(1)"), null);
});

test("each screen counts as its own page under the site's path", () => {
  assert.deepEqual(pagePath("/SiteScore/", "home"), { path: "/SiteScore/", title: "SiteScore · Home" });
  assert.deepEqual(pagePath("/SiteScore/", "workspace"), {
    path: "/SiteScore/#workspace",
    title: "SiteScore · Workspace",
  });
  assert.equal(pagePath("/", "evidence").path, "/#evidence");
});
