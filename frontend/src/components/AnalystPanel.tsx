import { useCallback, useEffect, useRef, useState } from "react";
import {
  type AnalystStatus,
  type Brief,
  type ChatMessage,
  type Step,
  type UiAction,
  type WorkspaceContext,
  analystMode,
  applyEvent,
  askAnalyst,
  briefMarkdown,
  findReplay,
  messageText,
} from "../lib/analyst";
import { OPENROUTER_KEYS_URL, REPO_URL } from "../lib/project";
import {
  IconArrowRight,
  IconArrowUpRight,
  IconGithub,
  IconChat,
  IconCheck,
  IconCopy,
  IconDownload,
  IconKey,
  IconPin,
  IconRefresh,
  IconSend,
  IconStop,
  IconX,
} from "./Icons";
import { Markdown } from "./Markdown";

interface Props {
  status: AnalystStatus | null;
  /** Business type id: recorded runs exist per type. */
  businessType: string;
  businessName: string;
  siteCount: number;
  getWorkspace: () => WorkspaceContext;
  onAction: (action: UiAction) => void;
  /** A question asked elsewhere (the home page); sent once when `key` changes. */
  incoming?: { question: string; key: number } | null;
}

let nextMsg = 1;
const msgId = () => `m${nextMsg++}`;

function suggestions(business: string, siteCount: number): string[] {
  const b = business.toLowerCase();
  if (siteCount > 0) {
    return [
      "Why does the top site win, and what would flip the ranking?",
      "Stress-test my sites with rent 30% higher and wages at $30k a month",
      "Find a cheaper spot within 800 m of my best site that keeps most of the revenue",
      "Write a decision brief for my shortlist",
    ];
  }
  return [
    `Find the best ${b} spot within 1 km of Parramatta station, ranked by profit`,
    "Compare Church St Parramatta, Harris Park and Wentworth Point",
    "Are any vacant shopfronts near Westmead Hospital worth a look?",
    "How accurate is SiteScore? Should I trust it?",
  ];
}

export function AnalystPanel({ status, businessType, businessName, siteCount, getWorkspace, onAction, incoming }: Props) {
  const mode = analystMode(status);
  const recorded = (status?.replays ?? []).filter((r) => r.business_type === businessType).map((r) => r.question);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const stick = useRef(true);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // Follow the answer as it streams, unless the reader has scrolled up.
  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy || !mode || mode === "off") return;
      const history = messagesRef.current
        .filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: messageText(m) }))
        .filter((m) => m.content);
      const user: ChatMessage = { id: msgId(), role: "user", parts: [{ kind: "text", text: q }] };
      // The hosted demo has no model: anything it hasn't recorded gets the "run it yourself" card.
      if (mode === "replay" && !findReplay(status, q, getWorkspace().business_type)) {
        const card: ChatMessage = { id: msgId(), role: "assistant", parts: [{ kind: "byok", question: q }] };
        setMessages((prev) => [...prev, user, card]);
        setDraft("");
        if (input.current) input.current.style.height = "auto";
        stick.current = true;
        return;
      }
      const reply: ChatMessage = { id: msgId(), role: "assistant", parts: [], pending: true };
      setMessages((prev) => [...prev, user, reply]);
      setDraft("");
      if (input.current) input.current.style.height = "auto"; // shrink back after a long question
      setBusy(true);
      stick.current = true;
      const ctrl = new AbortController();
      abort.current = ctrl;
      const update = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) => prev.map((m) => (m.id === reply.id ? fn(m) : m)));
      try {
        await askAnalyst({ question: q, history, workspace: getWorkspace() }, (ev) => {
          if (ev.event === "ui") onAction(ev.data);
          update((m) => applyEvent(m, ev));
        }, ctrl.signal);
        update((m) => ({ ...m, pending: false }));
      } catch (e) {
        const err = e as Error;
        update((m) => ({
          ...m,
          pending: false,
          error: err.name === "AbortError" ? undefined : err.message,
          parts: err.name === "AbortError" ? [...m.parts, { kind: "text", text: "_Stopped._" }] : m.parts,
        }));
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [busy, mode, status, getWorkspace, onAction],
  );

  const lastIncoming = useRef<number | null>(null);
  useEffect(() => {
    if (!incoming || incoming.key === lastIncoming.current || !mode || mode === "off") return;
    lastIncoming.current = incoming.key;
    void send(incoming.question);
  }, [incoming, mode, send]);

  const reset = () => {
    abort.current?.abort();
    setMessages([]);
    input.current?.focus();
  };

  if (status && mode === "off") return <AnalystOff model={status.model} />;

  return (
    <div className="analyst">
      <div className="analyst__head">
        <div className="analyst__title">
          <span className="muted small">{mode === "replay" ? "Recorded" : "Model"}</span>
          <span className="analyst__model">{status ? status.model : "connecting…"}</span>
        </div>
        {messages.length > 0 && (
          <button className="icon-btn" onClick={reset} title="New conversation" aria-label="New conversation">
            <IconRefresh size={16} />
          </button>
        )}
      </div>

      <div
        className="analyst__scroll"
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        aria-live="polite"
      >
        {messages.length === 0 && mode === "replay" ? (
          <div className="analyst__intro">
            <span className="mono analyst__kicker">demo/recorded_runs</span>
            <h3>Watch the analyst work</h3>
            <p className="muted small">
              This hosted demo doesn't call a language model. Pick a question to replay a real run: every step, map
              action and the decision brief, exactly as the analyst produced them. Ask anything else to see how to run
              your own.
            </p>
            {recorded.length > 0 ? (
              <ul className="suggestions">
                {recorded.map((s) => (
                  <li key={s}>
                    <button className="suggestion" onClick={() => send(s)}>
                      <span>{s}</span>
                      <IconArrowRight size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">The recordings are for cafés: switch the business type to Café to watch one.</p>
            )}
          </div>
        ) : messages.length === 0 ? (
          <div className="analyst__intro">
            <h3>Ask a location question</h3>
            <p className="muted small">
              The analyst searches areas, simulates sites over 36 months, tests what-ifs, puts its shortlist on the map and
              writes a brief. Every figure comes from SiteScore's model.
            </p>
            <span className="list-label">Try</span>
            <ul className="suggestions">
              {suggestions(businessName, siteCount).map((s) => (
                <li key={s}>
                  <button className="suggestion" onClick={() => send(s)} disabled={!status}>
                    <span>{s}</span>
                    <IconArrowRight size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          messages.map((m) => <Message key={m.id} msg={m} onAction={onAction} recorded={recorded} onPick={send} />)
        )}
      </div>

      <form
        className={`composer ${busy ? "is-busy" : ""}`}
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <textarea
          ref={input}
          value={draft}
          rows={1}
          placeholder={busy ? "Working…" : mode === "replay" ? "Ask your own question…" : "Ask a question…"}
          onChange={(e) => {
            setDraft(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(draft);
            }
          }}
          aria-label="Ask the AI analyst"
          disabled={!status}
        />
        {busy ? (
          <button type="button" className="composer__btn is-stop" onClick={() => abort.current?.abort()} aria-label="Stop">
            <IconStop size={16} />
          </button>
        ) : (
          <button type="submit" className="composer__btn" disabled={!draft.trim() || !status} aria-label="Send">
            <IconSend size={16} />
          </button>
        )}
      </form>
    </div>
  );
}

function Message({ msg, onAction, recorded, onPick }: {
  msg: ChatMessage;
  onAction: (a: UiAction) => void;
  recorded: string[];
  onPick: (question: string) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="msg msg--user">
        <div className="bubble">{messageText(msg)}</div>
      </div>
    );
  }
  const thinking = msg.pending && !msg.parts.some((p) => p.kind === "text" && p.text.trim());
  const running = msg.parts.some((p) => p.kind === "steps" && p.steps.some((s) => s.status === "running"));
  return (
    <div className="msg msg--ai">
      {msg.recorded && (
        <span className="recorded-tag mono">
          recorded_run · {new Date(`${msg.recorded.on}T00:00:00`).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" })}
          {msg.recorded.model && ` · ${msg.recorded.model}`}
        </span>
      )}
      {msg.parts.map((p, i) =>
        p.kind === "text" ? (
          <Markdown key={i} text={p.text} />
        ) : p.kind === "steps" ? (
          <Steps key={i} steps={p.steps} />
        ) : p.kind === "byok" ? (
          <ByokCard key={i} recorded={recorded} onPick={onPick} />
        ) : (
          <BriefCard key={i} brief={p.brief} onAction={onAction} />
        ),
      )}
      {thinking && !running && (
        <div className="thinking">
          <span className="thinking__dots" aria-hidden>
            <i />
            <i />
            <i />
          </span>
          {msg.parts.length ? "Reading the results…" : "Planning…"}
        </div>
      )}
      {msg.error && (
        <div className="msg-error" role="alert">
          <IconX size={14} /> {msg.error}
        </div>
      )}
    </div>
  );
}

function Steps({ steps }: { steps: Step[] }) {
  return (
    <ol className="steps">
      {steps.map((s) => (
        <li key={s.id} className={`step is-${s.status}`}>
          <span className="step__icon" aria-hidden>
            {s.status === "running" ? <span className="spinner spinner--sm" /> : s.status === "ok" ? <IconCheck size={13} /> : <IconX size={13} />}
          </span>
          <span className="step__body">
            <span className="step__label">{s.label}</span>
            {s.summary && <span className="step__summary">{s.summary}</span>}
          </span>
          {s.ms !== undefined && <span className="step__ms">{s.ms < 1000 ? `${s.ms} ms` : `${(s.ms / 1000).toFixed(1)} s`}</span>}
        </li>
      ))}
    </ol>
  );
}

export function BriefCard({ brief: b, onAction }: { brief: Brief; onAction: (a: UiAction) => void }) {
  const [copied, setCopied] = useState(false);
  const md = briefMarkdown(b);
  const download = () => {
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${b.title.replace(/[^\w-]+/g, "-").replace(/^-|-$/g, "").toLowerCase() || "site-brief"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked: the download still works
    }
  };
  return (
    <article className="brief">
      <header className="brief__head">
        <span className="brief__kicker">Decision brief</span>
        <h3>{b.title}</h3>
      </header>
      <p className="brief__verdict">{b.verdict}</p>
      {b.recommended && (
        <button
          className="brief__rec"
          onClick={() => onAction({ type: "focus", lat: b.recommended!.lat, lon: b.recommended!.lon, label: b.recommended!.label })}
        >
          <IconPin size={15} />
          <span>
            <span className="muted small">Recommended</span>
            <strong>{b.recommended.label}</strong>
          </span>
        </button>
      )}
      {b.key_numbers.length > 0 && (
        <dl className="brief__numbers">
          {b.key_numbers.map((k, i) => (
            <div key={i}>
              <dt>{k.label}</dt>
              <dd>{k.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <BriefList title="Why" items={b.reasons} />
      <BriefList title="Risks" items={b.risks} />
      <BriefList title="Check before signing" items={b.next_steps} />
      <footer className="brief__actions">
        <button className="btn btn--small" onClick={download}>
          <IconDownload size={14} /> Download .md
        </button>
        <button className="btn btn--small btn--ghost" onClick={copy}>
          {copied ? <IconCheck size={14} /> : <IconCopy size={14} />} {copied ? "Copied" : "Copy"}
        </button>
      </footer>
    </article>
  );
}

function BriefList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section className="brief__list">
      <h4>{title}</h4>
      <ul>
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </section>
  );
}

const RUN_LOCALLY = `git clone ${REPO_URL}.git
cd SiteScore
python run.py install
# then put OPENROUTER_API_KEY=sk-or-... in .env (copy .env.example)
python run.py start`;

/** The hosted demo can't answer a new question: here's how to run SiteScore with your own key. */
function ByokCard({ recorded, onPick }: { recorded: string[]; onPick: (q: string) => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(RUN_LOCALLY);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked: the commands are on screen
    }
  };
  return (
    <article className="byok">
      <span className="mono byok__kicker">run_it_yourself/</span>
      <h3>Ask your own questions on your machine</h3>
      <p className="muted small">
        This hosted demo doesn't call a language model, so it can only replay recorded runs. Run SiteScore locally with
        your own OpenRouter key (any tool-calling model; about a cent per question) and the analyst will answer anything.
      </p>
      <ol className="byok__steps">
        <li>
          <span>Get the code and install</span>
          <code>git clone {REPO_URL}.git</code>
          <code>cd SiteScore &amp;&amp; python run.py install</code>
        </li>
        <li>
          <span>
            Add your key to <code>.env</code>
          </span>
          <code>OPENROUTER_API_KEY=sk-or-…</code>
        </li>
        <li>
          <span>Start it</span>
          <code>python run.py start</code>
        </li>
      </ol>
      <div className="byok__actions">
        <a className="btn btn--small btn--accent" href={REPO_URL} target="_blank" rel="noreferrer">
          <IconGithub size={14} /> Get the code
        </a>
        <a className="btn btn--small" href={OPENROUTER_KEYS_URL} target="_blank" rel="noreferrer">
          Get a key <IconArrowUpRight size={14} />
        </a>
        <button className="btn btn--small btn--ghost" onClick={copy}>
          {copied ? <IconCheck size={14} /> : <IconCopy size={14} />} {copied ? "Copied" : "Copy commands"}
        </button>
      </div>
      {recorded.length > 0 && (
        <>
          <span className="mono byok__kicker">or_watch_a_recorded_run/</span>
          <ul className="suggestions">
            {recorded.map((s) => (
              <li key={s}>
                <button className="suggestion" onClick={() => onPick(s)}>
                  <span>{s}</span>
                  <IconArrowRight size={14} />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}

function AnalystOff({ model }: { model: string }) {
  return (
    <div className="analyst analyst--off">
      <div className="analyst__intro">
        <span className="icon-tile" aria-hidden>
          <IconChat size={18} />
        </span>
        <h3>Turn on the analyst</h3>
        <p className="muted">
          The analyst plans an investigation and runs SiteScore's model, spot finder and backtest for you, then puts its
          shortlist on the map and writes a decision brief. It uses any tool-calling language model through OpenRouter.
        </p>
        <ol className="setup">
          <li>
            <IconKey size={15} />
            <span>
              Create a key at{" "}
              <a href={OPENROUTER_KEYS_URL} target="_blank" rel="noreferrer">
                openrouter.ai/keys
              </a>
            </span>
          </li>
          <li>
            <IconCheck size={15} />
            <span>
              Add <code>OPENROUTER_API_KEY=…</code> to <code>.env</code> (optional: <code>OPENROUTER_MODEL={model}</code>)
            </span>
          </li>
          <li>
            <IconRefresh size={15} />
            <span>
              Restart with <code>python run.py start</code>
            </span>
          </li>
        </ol>
        <p className="muted small">Everything else works without it: add sites on the left, or search an area with Find spots.</p>
      </div>
    </div>
  );
}
