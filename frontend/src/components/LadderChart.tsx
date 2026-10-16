import { useState } from "react";
import { pct } from "../lib/format";
import { ladderVerdict } from "../lib/ladder";
import type { LadderStep, OutcomeComparison } from "../lib/types";

const TICKS = [-1, -0.5, 0, 0.5, 1];
const x = (v: number) => ((Math.max(-1, Math.min(1, v)) + 1) / 2) * 100; // Spearman -> % across

const num = (v: number | null) => (v === null ? "n/a" : (v >= 0 ? "" : "−") + Math.abs(v).toFixed(2));
const signed = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2);
const interval = (ci: [number, number] | null) => (ci ? `${num(ci[0])} to ${num(ci[1])}` : "");
/** Does some rung's gain over foot traffic have a 90% interval clear of zero? */
const hasLead = (c: OutcomeComparison) => c.steps.some((s) => s.gain_ci && s.gain_ci[0] > 0);

export { ladderVerdict } from "../lib/ladder";

/**
 * Which layers help: one outcome at a time, picked from a strip of tabs, so each
 * ladder gets the full width. Every rung keeps its value, 90% interval and gain over
 * foot traffic; the verdict and how to read it sit beside the chart.
 */
export function LadderExplorer({ ladder }: { ladder: OutcomeComparison[] }) {
  const available = ladder.filter((o) => o.available);
  const missing = ladder.filter((o) => !o.available);
  const [pick, setPick] = useState(0);
  const current = available[Math.min(pick, available.length - 1)];

  return (
    <div className="lx">
      <div className="lx__tabs" role="tablist" aria-label="Outcome">
        {available.map((c, i) => (
          <button
            key={c.outcome}
            role="tab"
            aria-selected={c === current}
            className={`lx__tab ${c === current ? "is-on" : ""}`}
            onClick={() => setPick(i)}
          >
            <span className="lx__n mono">{String(i + 1).padStart(2, "0")}</span>
            <span className="lx__label">{c.label}</span>
            <span className="lx__meta mono">
              {c.steps[0]?.n ?? 0} businesses · <span className={hasLead(c) ? "is-lead" : ""}>{hasLead(c) ? "a lead" : "no clear gain"}</span>
            </span>
          </button>
        ))}
      </div>
      {current && <LadderPanel key={current.outcome} comparison={current} />}
      {missing.length > 0 && (
        <ul className="lx__missing muted small">
          {missing.map((o) => (
            <li key={o.outcome}>
              <span className="mono">not_compared/</span> {o.label}: {o.note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LadderPanel({ comparison }: { comparison: OutcomeComparison }) {
  const [hover, setHover] = useState<number | null>(null);
  const steps = comparison.steps;
  const base = steps[0]?.spearman ?? null;
  const full = steps.find((s) => s.key === "full") ?? steps[steps.length - 1];

  return (
    <div className="lx__panel">
      <div className="lx__chart" role="table" aria-label={`How each model layer ranks: ${comparison.label}`}>
        <div className="lx__row lx__row--head" role="row">
          <span role="columnheader">#</span>
          <span role="columnheader">Model, adding layers</span>
          <span role="columnheader">Spearman with the outcome</span>
          <span role="columnheader" className="num">ρ</span>
          <span role="columnheader" className="num">90% interval</span>
          <span role="columnheader" className="num">Gain vs foot traffic</span>
        </div>
        {steps.map((s, i) => (
          <Rung key={s.key} step={s} index={i} base={base} active={hover === i} onHover={(on) => setHover(on ? i : null)} />
        ))}
        <div className="lx__row lx__row--axis" aria-hidden>
          <span />
          <span />
          <span className="lx__ticks">
            {TICKS.map((t) => (
              <span key={t} style={{ left: `${x(t)}%` }}>
                {t === 0 ? "0" : num(t)}
              </span>
            ))}
          </span>
        </div>
      </div>
      <aside className="lx__aside">
        <span className="mono lx__kicker">verdict/</span>
        <p>{ladderVerdict(comparison)}</p>
        <span className="mono lx__kicker">sample/</span>
        <dl className="lx__facts">
          <div>
            <dt>Businesses</dt>
            <dd className="num">{steps[0]?.n ?? 0}</dd>
          </div>
          <div>
            <dt>Pairs compared</dt>
            <dd className="num">{steps[0]?.pairs ?? 0}</dd>
          </div>
          <div>
            <dt>Full model, pairs in order</dt>
            <dd className="num">{full?.pairwise_accuracy == null ? "n/a" : pct(full.pairwise_accuracy)}</dd>
          </div>
        </dl>
        <span className="mono lx__kicker">how_to_read/</span>
        <p className="muted small">
          0 = no relation; 1 = the same order as reality. Each bar is a 90% interval: where the value could land with a
          different sample of the same size. A gain only counts when its interval clears zero.
        </p>
      </aside>
    </div>
  );
}

function Rung({ step: s, index, base, active, onHover }: {
  step: LadderStep; index: number; base: number | null; active: boolean; onHover: (on: boolean) => void;
}) {
  const ci = s.spearman_ci;
  const first = index === 0;
  const clear = !!s.gain_ci && s.gain_ci[0] > 0;
  return (
    <div
      className={`lx__row ${active ? "is-active" : ""} ${first ? "is-baseline" : ""}`}
      role="row"
      tabIndex={0}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onFocus={() => onHover(true)}
      onBlur={() => onHover(false)}
    >
      <span role="cell" className="lx__step mono">{String(index + 1).padStart(2, "0")}</span>
      <span role="cell" className="lx__layer">
        {s.label}
        {first && <span className="tag">baseline</span>}
      </span>
      <span role="cell" className="lx__plot">
        {TICKS.map((t) => (
          <span key={t} className={`lx__grid ${t === 0 ? "is-zero" : ""}`} style={{ left: `${x(t)}%` }} />
        ))}
        {ci && <span className="lx__ci" style={{ left: `${x(ci[0])}%`, width: `${x(ci[1]) - x(ci[0])}%` }} />}
        {s.spearman !== null && <span className="lx__dot" style={{ left: `${x(s.spearman)}%` }} />}
        {active && (
          <span className="ladder-tip" role="tooltip">
            <strong>{s.label}</strong>
            <span>Spearman {num(s.spearman)}{ci ? ` (90%: ${interval(ci)})` : ""}</span>
            <span>Pairs ordered correctly {s.pairwise_accuracy === null ? "n/a" : pct(s.pairwise_accuracy)} of {s.pairs}</span>
            {s.gain_ci && <span>Gain over foot traffic: {interval(s.gain_ci)}</span>}
          </span>
        )}
      </span>
      <span role="cell" className="num lx__rho">{num(s.spearman)}</span>
      <span role="cell" className="num lx__ci-text muted">{interval(ci)}</span>
      <span role="cell" className={`num lx__gain ${clear ? "is-clear" : ""}`}>
        {first || base === null || s.spearman === null ? (
          <span className="muted">–</span>
        ) : (
          <>
            <strong>{signed(s.spearman - base)}</strong>
            {s.gain_ci && <span className="muted small">{interval(s.gain_ci)}</span>}
          </>
        )}
      </span>
    </div>
  );
}
