// Run with `npm test` (Node's built-in runner; Node 22.6+ strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";

import { type AnalystEvent, type ChatMessage, applyEvent, messageText, parseSSE } from "./analyst.ts";

const empty = (): ChatMessage => ({ id: "a", role: "assistant", parts: [], pending: true });
const play = (events: AnalystEvent[]) => events.reduce(applyEvent, empty());

test("SSE parsing keeps the unfinished tail for the next chunk", () => {
  const { events, rest } = parseSSE('event: text\ndata: {"delta":"Hi"}\n\nevent: done\ndata: {"st');
  assert.deepEqual(events, [{ event: "text", data: { delta: "Hi" } }]);
  assert.equal(rest, 'event: done\ndata: {"st');
});

test("text, steps and more text stay in order", () => {
  const msg = play([
    { event: "text", data: { delta: "Let me " } },
    { event: "text", data: { delta: "check." } },
    { event: "step", data: { id: "1", name: "geocode", label: "Looking up" } },
    { event: "step", data: { id: "2", name: "find_spots", label: "Scanning" } },
    { event: "step_done", data: { id: "1", name: "geocode", ok: true, summary: "Found", ms: 20 } },
    { event: "text", data: { delta: "Done." } },
    { event: "done", data: { steps: 2 } },
  ]);
  assert.deepEqual(msg.parts.map((p) => p.kind), ["text", "steps", "text"]);
  const steps = msg.parts[1].kind === "steps" ? msg.parts[1].steps : [];
  assert.deepEqual(steps.map((s) => s.status), ["ok", "running"]);
  assert.equal(messageText(msg), "Let me check.\n\nDone.");
  assert.equal(msg.pending, false);
});

test("a brief becomes part of the answer; other UI actions don't", () => {
  const brief = { title: "T", verdict: "V", recommended: null, key_numbers: [], reasons: [], risks: [], next_steps: [], business_type: "cafe", as_of: "2026-10-12" };
  const msg = play([
    { event: "ui", data: { type: "focus", lat: 0, lon: 0, label: "x" } },
    { event: "ui", data: { type: "brief", brief } },
  ]);
  assert.deepEqual(msg.parts, [{ kind: "brief", brief }]);
});

test("errors stop the spinner", () => {
  const msg = play([{ event: "error", data: { message: "OpenRouter 401" } }]);
  assert.equal(msg.error, "OpenRouter 401");
  assert.equal(msg.pending, false);
});

test("recorded questions match the way the server matches them", async () => {
  const { findReplay } = await import("./analyst.ts");
  const status = {
    enabled: false, mode: "replay" as const, model: "m", provider: "OpenRouter",
    replays: [{ question: "Find the best café spot within 1 km of Parramatta station, ranked by profit", business_type: "cafe", recorded_on: "2026-10-17" }],
  };
  assert.ok(findReplay(status, "find the BEST café spot within 1 km of Parramatta station ranked by profit!", "cafe"));
  assert.equal(findReplay(status, "Find the best café spot within 1 km of Parramatta station, ranked by profit", "gym"), undefined);
  assert.equal(findReplay(status, "Best café spot near Rosehill", "cafe"), undefined);
});

test("a replayed run is marked as recorded", () => {
  const msg = play([{ event: "status", data: { model: "m", replay: { recorded_on: "2026-10-17", model: "m" } } }]);
  assert.deepEqual(msg.recorded, { on: "2026-10-17", model: "m" });
});
