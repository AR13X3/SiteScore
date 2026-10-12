// Run with `npm test` (Node's built-in runner; Node 22.6+ strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { parseInline, parseMarkdown } from "./markdown.ts";

test("paragraphs, headings and emphasis", () => {
  const blocks = parseMarkdown("## Verdict\n\n**Church St** wins by *a lot*.");
  assert.equal(blocks[0].t, "h");
  assert.deepEqual(blocks[1], {
    t: "p",
    c: [
      { t: "strong", c: [{ t: "text", v: "Church St" }] },
      { t: "text", v: " wins by " },
      { t: "em", c: [{ t: "text", v: "a lot" }] },
      { t: "text", v: "." },
    ],
  });
});

test("tables keep their columns and alignment", () => {
  const [table] = parseMarkdown("| Site | Revenue |\n|---|---:|\n| A | $1.2M |\n| B |");
  assert.equal(table.t, "table");
  if (table.t !== "table") return;
  assert.deepEqual(table.align, [null, "right"]);
  assert.equal(table.rows.length, 2);
  assert.deepEqual(table.rows[1][1], []); // a short row is padded, not dropped
});

test("lists, ordered and not", () => {
  const blocks = parseMarkdown("- one\n- two\n\n1. first\n2. second");
  assert.deepEqual(blocks.map((b) => b.t), ["ul", "ol"]);
});

test("snake_case and unsafe links stay text", () => {
  assert.deepEqual(parseInline("rent_per_month"), [{ t: "text", v: "rent_per_month" }]);
  const nodes = parseInline("[x](javascript:alert(1))");
  assert.ok(nodes.every((n) => n.t === "text"));
});

test("unfinished syntax while streaming is plain text", () => {
  assert.deepEqual(parseInline("**Chur"), [{ t: "text", v: "**Chur" }]);
});
