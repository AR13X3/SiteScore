// The AI analyst's wire format (sitescore/analyst/agent.py) and the chat state built from it.

import type { Costs, SearchResult } from "./types";

/** A recorded run the hosted demo can replay (no model key needed). */
export interface ReplayInfo {
  question: string;
  business_type: string;
  recorded_on: string;
}

export interface AnalystStatus {
  enabled: boolean;
  /** "live": a model key is set. "replay": no key, recorded runs only. "off": neither. */
  mode?: "live" | "replay" | "off";
  model: string;
  provider: string;
  replays?: ReplayInfo[];
}

export const analystMode = (s: AnalystStatus | null): "live" | "replay" | "off" | null =>
  s ? (s.mode ?? (s.enabled ? "live" : "off")) : null;

/** Same rule as the server (analyst/replay.py): case, punctuation and spacing don't matter. */
export const normaliseQuestion = (q: string) =>
  q.toLowerCase().replace(/[^\p{L}\p{N}_\s]/gu, " ").replace(/\s+/g, " ").trim();

/** The recorded run for this question and business type, if there is one. */
export function findReplay(s: AnalystStatus | null, question: string, businessType: string): ReplayInfo | undefined {
  const key = normaliseQuestion(question);
  return s?.replays?.find((r) => r.business_type === businessType && normaliseQuestion(r.question) === key);
}

export interface WorkspaceContext {
  business_type: string;
  as_of: string | null;
  costs: Costs | null;
  sites: { id: string; label: string; lat: number; lon: number }[];
  selected_id: string | null;
  finder: { lat: number; lon: number; radius_m: number } | null;
}

export interface BriefSite {
  label: string;
  lat: number;
  lon: number;
}

export interface Brief {
  title: string;
  verdict: string;
  recommended: BriefSite | null;
  key_numbers: { label: string; value: string }[];
  reasons: string[];
  risks: string[];
  next_steps: string[];
  business_type: string;
  as_of: string;
}

/** Actions the analyst takes on the workspace. */
export type UiAction =
  | { type: "set_sites"; mode: "replace" | "add"; sites: BriefSite[] }
  | {
      type: "search";
      result: SearchResult;
      settings: { lat: number; lon: number; radius: number; where: SearchResult["where"]; retailOnly: boolean; rankBy: SearchResult["rank_by"] };
    }
  | { type: "focus"; lat: number; lon: number; label: string }
  | { type: "brief"; brief: Brief };

export type AnalystEvent =
  | { event: "status"; data: { model: string; replay?: { recorded_on: string; model: string } } }
  | { event: "text"; data: { delta: string } }
  | { event: "step"; data: { id: string; name: string; label: string } }
  | { event: "step_done"; data: { id: string; name: string; ok: boolean; summary: string; ms: number } }
  | { event: "ui"; data: UiAction }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { steps: number } };

export interface Step {
  id: string;
  name: string;
  label: string;
  status: "running" | "ok" | "error";
  summary?: string;
  ms?: number;
}

/** An assistant answer, in the order things happened. */
export type Part =
  | { kind: "text"; text: string }
  | { kind: "steps"; steps: Step[] }
  | { kind: "brief"; brief: Brief }
  /** The hosted demo can't answer this one: how to run SiteScore with your own key. */
  | { kind: "byok"; question: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  parts: Part[];
  error?: string;
  pending?: boolean;
  /** Set when the answer is a recorded run being replayed. */
  recorded?: { on: string; model: string };
}

/** Apply one streamed event to an assistant message (pure, so it can be tested). */
export function applyEvent(msg: ChatMessage, ev: AnalystEvent): ChatMessage {
  const parts = [...msg.parts];
  const last = parts[parts.length - 1];
  switch (ev.event) {
    case "status":
      return ev.data.replay ? { ...msg, recorded: { on: ev.data.replay.recorded_on, model: ev.data.replay.model } } : msg;
    case "text": {
      if (last?.kind === "text") parts[parts.length - 1] = { kind: "text", text: last.text + ev.data.delta };
      else if (ev.data.delta.trim()) parts.push({ kind: "text", text: ev.data.delta.trimStart() });
      return { ...msg, parts };
    }
    case "step": {
      const step: Step = { id: ev.data.id, name: ev.data.name, label: ev.data.label, status: "running" };
      // Consecutive tool calls share one timeline.
      if (last?.kind === "steps") parts[parts.length - 1] = { kind: "steps", steps: [...last.steps, step] };
      else parts.push({ kind: "steps", steps: [step] });
      return { ...msg, parts };
    }
    case "step_done":
      return {
        ...msg,
        parts: parts.map((p) =>
          p.kind === "steps"
            ? {
                kind: "steps",
                steps: p.steps.map((s) =>
                  s.id === ev.data.id ? { ...s, status: ev.data.ok ? "ok" : "error", summary: ev.data.summary, ms: ev.data.ms } : s,
                ),
              }
            : p,
        ),
      };
    case "ui":
      return ev.data.type === "brief" ? { ...msg, parts: [...parts, { kind: "brief", brief: ev.data.brief }] } : msg;
    case "error":
      return { ...msg, error: ev.data.message, pending: false };
    case "done":
      return { ...msg, pending: false };
    default:
      return msg;
  }
}

/** The text of a message, for history and copying. */
export function messageText(msg: ChatMessage): string {
  return msg.parts
    .filter((p): p is { kind: "text"; text: string } => p.kind === "text")
    .map((p) => p.text.trim())
    .join("\n\n");
}

/** Parse a server-sent-events buffer: complete events, plus the unfinished remainder. */
export function parseSSE(buffer: string): { events: AnalystEvent[]; rest: string } {
  const chunks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = chunks.pop() ?? "";
  const events: AnalystEvent[] = [];
  for (const chunk of chunks) {
    let name = "message";
    const data: string[] = [];
    for (const line of chunk.split("\n")) {
      if (line.startsWith("event: ")) name = line.slice(7).trim();
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (!data.length) continue;
    try {
      events.push({ event: name, data: JSON.parse(data.join("\n")) } as AnalystEvent);
    } catch {
      // a malformed event is skipped, not fatal
    }
  }
  return { events, rest };
}

/** POST a question and call `onEvent` for each event as it streams in. */
export async function askAnalyst(
  body: { question: string; history: { role: string; content: string }[]; workspace: WorkspaceContext },
  onEvent: (ev: AnalystEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/analyst/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      // keep the status line
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSSE(buffer);
    buffer = rest;
    events.forEach(onEvent);
  }
  parseSSE(`${buffer}\n\n`).events.forEach(onEvent);
}

/** A brief as a Markdown document (for download / copy). */
export function briefMarkdown(b: Brief): string {
  const list = (title: string, items: string[]) => (items.length ? `\n## ${title}\n\n${items.map((x) => `- ${x}`).join("\n")}\n` : "");
  const numbers = b.key_numbers.length
    ? `\n| | |\n|---|---|\n${b.key_numbers.map((k) => `| ${k.label} | ${k.value} |`).join("\n")}\n`
    : "";
  const rec = b.recommended
    ? `\n**Recommended site:** ${b.recommended.label} (${b.recommended.lat.toFixed(5)}, ${b.recommended.lon.toFixed(5)})\n`
    : "";
  return (
    `# ${b.title}\n\n_${b.business_type} · data as of ${b.as_of} · generated by the SiteScore AI analyst_\n\n` +
    `${b.verdict}\n${rec}${numbers}${list("Why", b.reasons)}${list("Risks", b.risks)}${list("Check before signing", b.next_steps)}` +
    `\n---\nSiteScore projections are model estimates from open data, not guarantees. See the Evidence page for how well the model has predicted real openings.\n`
  );
}
